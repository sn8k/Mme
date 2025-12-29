# -*- coding: utf-8 -*-
"""
Meeting API integration service for Motion Frontend.
Handles heartbeat signaling and device status reporting to Meeting server.

Version: 0.4.0
"""

import asyncio
import logging
import platform
import socket
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try to import aiohttp for async HTTP requests
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("aiohttp not available - Meeting service will use synchronous requests")

# Fallback to requests for sync HTTP
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class MeetingService:
    """
    Service for interacting with Meeting API.
    
    Handles:
    - Periodic heartbeat signaling (POST /api/devices/{device_key}/online)
    - Status reporting (IP addresses, services, device info, cameras)
    """
    
    def __init__(self) -> None:
        self._server_url = ""
        self._device_key = ""
        self._token_code = ""
        self._heartbeat_interval = 60  # seconds
        
        # Runtime state
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._last_heartbeat: Optional[datetime] = None
        self._last_heartbeat_success = False
        self._last_error: Optional[str] = None
        self._is_running = False
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Callback to get camera info from config_store
        self._get_cameras_callback: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self._get_http_port_callback: Optional[Callable[[], int]] = None
        
        # Cached public IP (fetched periodically)
        self._public_ip: Optional[str] = None
        self._public_ip_last_fetch: Optional[datetime] = None
    
    def set_callbacks(
        self,
        get_cameras: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        get_http_port: Optional[Callable[[], int]] = None
    ) -> None:
        """Set callbacks to retrieve dynamic information."""
        self._get_cameras_callback = get_cameras
        self._get_http_port_callback = get_http_port
    
    def configure(
        self,
        server_url: str,
        device_key: str,
        token_code: str,
        heartbeat_interval: int = 60
    ) -> None:
        """Configure the Meeting service."""
        self._server_url = server_url.rstrip('/') if server_url else ""
        self._device_key = device_key
        self._token_code = token_code
        self._heartbeat_interval = max(10, min(3600, heartbeat_interval))
        
        logger.info(
            "Meeting service configured: server=%s, device=%s, interval=%ds",
            self._server_url, self._device_key, self._heartbeat_interval
        )
    
    def is_configured(self) -> bool:
        """Check if Meeting service is properly configured."""
        return bool(self._server_url and self._device_key)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current Meeting service status."""
        return {
            "is_configured": self.is_configured(),
            "is_running": self._is_running,
            "server_url": self._server_url,
            "device_key": self._device_key,
            "heartbeat_interval": self._heartbeat_interval,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "last_heartbeat_success": self._last_heartbeat_success,
            "last_error": self._last_error,
        }
    
    async def start(self) -> bool:
        """Start the heartbeat service. Starts automatically if configured."""
        if not self._server_url or not self._device_key:
            logger.debug("Meeting service not configured (missing server_url or device_key)")
            self._last_error = "Configuration incomplète (URL ou Device Key manquant)"
            return False
        
        if self._is_running:
            logger.debug("Meeting heartbeat already running")
            return True
        
        if not AIOHTTP_AVAILABLE:
            logger.error("aiohttp not available, cannot start Meeting service")
            self._last_error = "aiohttp non disponible"
            return False
        
        logger.info("Starting Meeting heartbeat service (interval: %ds)", self._heartbeat_interval)
        self._is_running = True
        self._last_error = None
        
        # Create aiohttp session
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"}
        )
        
        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return True
    
    async def stop(self) -> None:
        """Stop the heartbeat service."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        
        if self._session:
            await self._session.close()
            self._session = None
        
        self._is_running = False
        logger.info("Meeting heartbeat service stopped")
    
    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop - sends periodic online signals."""
        logger.info("Meeting heartbeat loop started")
        
        # Send initial heartbeat immediately
        await self._send_heartbeat()
        
        while self._is_running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                logger.info("Heartbeat loop cancelled")
                break
            except Exception as e:
                logger.error("Heartbeat loop error: %s", e)
                self._last_error = str(e)
                await asyncio.sleep(10)  # Wait before retry on error
    
    async def _send_heartbeat(self) -> bool:
        """Send heartbeat to Meeting server with comprehensive device data."""
        if not self._session:
            return False
        
        url = f"{self._server_url}/api/devices/{self._device_key}/online"
        
        # Get IP addresses
        local_ip = self._get_local_ip()
        public_ip = await self._get_public_ip()
        
        # Get HTTP port from callback
        http_port = 8765
        if self._get_http_port_callback:
            try:
                http_port = self._get_http_port_callback()
            except Exception:
                pass
        
        # Get camera information from callback
        cameras_info = []
        if self._get_cameras_callback:
            try:
                cameras = self._get_cameras_callback()
                for cam in cameras:
                    cam_id = cam.get("id", "1")
                    cameras_info.append({
                        "id": cam_id,
                        "name": cam.get("name", f"Camera {cam_id}"),
                        "enabled": cam.get("enabled", True),
                        "stream_url": f"/stream/{cam_id}/"
                    })
            except Exception as e:
                logger.debug("Could not get camera info: %s", e)
        
        # Build comprehensive payload
        payload = {
            "ip_address": local_ip,
            "public_ip": public_ip,
            "hostname": self._get_hostname(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "python": platform.python_version()
            },
            "services": {
                "ssh": 22,
                "http": http_port,
                "vnc": 0,
                "mjpeg": 8081
            },
            "cameras": cameras_info,
            "note": f"Motion Frontend - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
        
        try:
            async with self._session.post(url, json=payload) as response:
                self._last_heartbeat = datetime.now()
                
                if response.status == 200:
                    data = await response.json()
                    self._last_heartbeat_success = True
                    self._last_error = None
                    logger.debug("Heartbeat sent successfully: %s", data)
                    return True
                else:
                    error_text = await response.text()
                    self._last_heartbeat_success = False
                    self._last_error = f"HTTP {response.status}: {error_text[:100]}"
                    logger.warning("Heartbeat failed: %s", self._last_error)
                    return False
                    
        except aiohttp.ClientError as e:
            self._last_heartbeat = datetime.now()
            self._last_heartbeat_success = False
            self._last_error = f"Erreur réseau: {str(e)}"
            logger.error("Heartbeat network error: %s", e)
            return False
        except Exception as e:
            self._last_heartbeat = datetime.now()
            self._last_heartbeat_success = False
            self._last_error = f"Erreur: {str(e)}"
            logger.error("Heartbeat error: %s", e)
            return False
    
    async def _get_public_ip(self) -> Optional[str]:
        """Get public IP address (cached for 5 minutes)."""
        now = datetime.now()
        
        # Return cached IP if still valid (5 min cache)
        if (self._public_ip and self._public_ip_last_fetch and 
            (now - self._public_ip_last_fetch).total_seconds() < 300):
            return self._public_ip
        
        # Try to fetch public IP from external service
        public_ip_services = [
            "https://api.ipify.org?format=json",
            "https://httpbin.org/ip",
            "https://api.my-ip.io/v2/ip.json"
        ]
        
        for service_url in public_ip_services:
            try:
                async with self._session.get(service_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Handle different response formats
                        ip = data.get("ip") or data.get("origin") or data.get("ip_address")
                        if ip:
                            self._public_ip = ip.split(",")[0].strip()  # Handle multiple IPs
                            self._public_ip_last_fetch = now
                            logger.debug("Public IP fetched: %s", self._public_ip)
                            return self._public_ip
            except Exception as e:
                logger.debug("Failed to fetch public IP from %s: %s", service_url, e)
                continue
        
        return self._public_ip  # Return last known or None
    
    def _get_hostname(self) -> str:
        """Get device hostname."""
        try:
            return socket.gethostname()
        except Exception:
            return "unknown"
            return False
    
    def _get_local_ip(self) -> str:
        """Get the local IP address."""
        try:
            # Create a socket to determine the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    async def send_manual_heartbeat(self) -> Dict[str, Any]:
        """Send a manual heartbeat (for testing/forcing)."""
        if not self.is_configured():
            return {"success": False, "error": "Service non configuré"}
        
        if not self._session:
            # Create temporary session for manual heartbeat
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"}
            ) as session:
                self._session = session
                result = await self._send_heartbeat()
                self._session = None
                return {
                    "success": result,
                    "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
                    "error": self._last_error
                }
        else:
            result = await self._send_heartbeat()
            return {
                "success": result,
                "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
                "error": self._last_error
            }


# Global Meeting service instance
_meeting_service: Optional[MeetingService] = None


def get_meeting_service() -> MeetingService:
    """Get the global Meeting service instance."""
    global _meeting_service
    if _meeting_service is None:
        _meeting_service = MeetingService()
    return _meeting_service


def is_aiohttp_available() -> bool:
    """Check if aiohttp is available."""
    return AIOHTTP_AVAILABLE
