# File Version: 0.30.8
from __future__ import annotations

import json
import logging
import os
import socket
import glob
import platform
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import updater
from . import system_info

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/motion_frontend.json")
CAMERAS_CONFIG_DIR = Path("config/cameras")
AUDIO_CONFIG_DIR = Path("config/audio")


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int, returning default if empty or invalid."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _get_server_port() -> int:
    """Get the server port from environment or default."""
    return int(os.getenv("MFE_PORT", "8765"))


def _get_local_ip() -> str:
    """Get the local IP address of the server."""
    try:
        # Create a socket to determine the local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ============================================================================
# Stable Device Path Resolution (survives reboots)
# ============================================================================

def resolve_video_device(device_path: str, stable_path: str = "") -> str:
    """Resolve the best video device path to use.
    
    On Linux, /dev/videoX numbers change between reboots. This function:
    1. If stable_path is set, resolve it to current /dev/videoX
    2. If stable_path doesn't exist, try to find it from device_path
    3. Convert numeric index to /dev/videoN on Linux
    4. Fall back to device_path if nothing else works
    
    Args:
        device_path: The configured device path (e.g., /dev/video0 or "0")
        stable_path: The stable path from /dev/v4l/by-id/ or /dev/v4l/by-path/
        
    Returns:
        The actual device path to use for capture.
    """
    is_linux = platform.system().lower() == "linux"
    
    # On Linux, convert numeric index to /dev/videoN
    if is_linux:
        try:
            device_index = int(device_path)
            device_path = f"/dev/video{device_index}"
            logger.debug("Converted numeric device index %d to %s", device_index, device_path)
        except ValueError:
            pass  # Not a numeric index, keep as-is
    
    if not is_linux:
        return device_path
    
    # If we have a stable path, resolve it to the current /dev/videoX
    if stable_path and os.path.exists(stable_path):
        try:
            resolved = os.path.realpath(stable_path)
            if os.path.exists(resolved):
                logger.debug("Resolved stable path %s -> %s", stable_path, resolved)
                return resolved
        except Exception as e:
            logger.warning("Failed to resolve stable path %s: %s", stable_path, e)
    
    # If device_path exists directly, use it
    if device_path and os.path.exists(device_path):
        return device_path
    
    # Last resort: return the device_path even if it doesn't exist
    # (caller will get an error, which is better than silently using wrong device)
    logger.warning("Video device not found: %s (stable: %s)", device_path, stable_path)
    return device_path


def find_stable_video_path(device_path: str) -> str:
    """Find the stable path for a video device.
    
    Args:
        device_path: The dynamic device path (e.g., /dev/video0)
        
    Returns:
        Stable path from /dev/v4l/by-id/ or /dev/v4l/by-path/, empty string if not found.
    """
    if platform.system().lower() != "linux":
        return ""
    
    if not device_path or not os.path.exists(device_path):
        return ""
    
    try:
        real_device = os.path.realpath(device_path)
        
        # Prefer by-id (based on device serial/model) over by-path (USB port location)
        for search_dir in ["/dev/v4l/by-id", "/dev/v4l/by-path"]:
            if not os.path.isdir(search_dir):
                continue
            
            for symlink in glob.glob(f"{search_dir}/*"):
                try:
                    if os.path.realpath(symlink) == real_device:
                        logger.debug("Found stable video path: %s -> %s", device_path, symlink)
                        return symlink
                except Exception:
                    continue
    except Exception as e:
        logger.debug("Error finding stable path for %s: %s", device_path, e)
    
    return ""


def resolve_audio_device(device_id: str, stable_id: str = "") -> str:
    """Resolve the best audio device ID to use.
    
    On Linux, ALSA device numbers (hw:X,Y) change between reboots. This function:
    1. If stable_id is set, find the current hw:X,Y for that card name
    2. Fall back to device_id if stable_id resolution fails
    
    Args:
        device_id: The configured device ID (e.g., hw:1,0)
        stable_id: The stable identifier (card name, e.g., "HD-5000")
        
    Returns:
        The actual ALSA device ID to use for capture.
    """
    if platform.system().lower() != "linux":
        return device_id
    
    if not stable_id:
        return device_id
    
    try:
        # Parse /proc/asound/cards to find the card number by name
        cards_path = "/proc/asound/cards"
        if os.path.exists(cards_path):
            with open(cards_path, "r") as f:
                content = f.read()
            
            # Format: " 0 [PCH            ]: HDA-Intel - HDA Intel PCH"
            import re
            for match in re.finditer(r"\s*(\d+)\s+\[([^\]]+)\]:\s+([^\-]+)\s+-\s+(.+)", content):
                card_num = match.group(1).strip()
                card_id = match.group(2).strip()
                driver = match.group(3).strip()
                card_name = match.group(4).strip()
                
                # Check if the stable_id matches any part of the card info
                if (stable_id.lower() in card_name.lower() or 
                    stable_id.lower() in card_id.lower() or
                    stable_id == card_num):
                    resolved = f"hw:{card_num},0"
                    logger.debug("Resolved audio stable_id '%s' -> %s (card: %s)", 
                               stable_id, resolved, card_name)
                    return resolved
    except Exception as e:
        logger.warning("Failed to resolve audio stable_id '%s': %s", stable_id, e)
    
    # Fall back to original device_id
    return device_id


def find_stable_audio_id(device_id: str) -> str:
    """Find a stable identifier for an ALSA audio device.
    
    Args:
        device_id: The dynamic device ID (e.g., hw:1,0)
        
    Returns:
        Stable identifier (card name), empty string if not found.
    """
    if platform.system().lower() != "linux":
        return ""
    
    if not device_id:
        return ""
    
    try:
        import re
        # Extract card number from hw:X,Y
        match = re.match(r"hw:(\d+)", device_id)
        if not match:
            return ""
        
        card_num = match.group(1)
        
        # Read card name from /proc/asound/cards
        cards_path = "/proc/asound/cards"
        if os.path.exists(cards_path):
            with open(cards_path, "r") as f:
                content = f.read()
            
            for line_match in re.finditer(r"\s*(\d+)\s+\[([^\]]+)\]:\s+([^\-]+)\s+-\s+(.+)", content):
                if line_match.group(1).strip() == card_num:
                    card_name = line_match.group(4).strip()
                    logger.debug("Found stable audio ID: %s -> '%s'", device_id, card_name)
                    return card_name
    except Exception as e:
        logger.debug("Error finding stable audio ID for %s: %s", device_id, e)
    
    return ""


@dataclass
class CameraConfig:
    identifier: str
    name: str
    enabled: bool = True
    device_settings: Dict[str, str] = field(default_factory=dict)
    # Extended camera settings
    stream_url: str = ""
    mjpeg_port: int = 8081
    # Video input settings (camera capture)
    resolution: str = "1280x720"
    framerate: int = 15
    rotation: int = 0
    brightness: int = 0
    contrast: int = 0
    saturation: int = 0
    # Streaming output settings
    stream_resolution: str = "1280x720"
    stream_framerate: int = 15
    jpeg_quality: int = 80
    stream_auth_enabled: bool = False  # HTTP Basic auth for stream access
    # Motion detection
    motion_detection_enabled: bool = True
    motion_threshold: int = 1500
    motion_frames: int = 1
    # Recording
    record_movies: bool = True
    record_stills: bool = False
    pre_capture: int = 0
    post_capture: int = 0
    # Text overlay settings
    overlay_left_text: str = "disabled"  # camera_name, timestamp, custom, capture_info, disabled
    overlay_left_custom: str = ""
    overlay_right_text: str = "timestamp"  # camera_name, timestamp, custom, capture_info, disabled
    overlay_right_custom: str = ""
    overlay_text_scale: int = 3  # 1-10
    # Stream source settings (auto = Motion if running else internal, internal = our MJPEG server, motion = Motion's stream)
    stream_source: str = "auto"  # "auto", "internal" or "motion"
    motion_stream_port: int = 8081  # Port where Motion exposes its stream
    # RTSP streaming settings
    rtsp_enabled: bool = False
    rtsp_audio_device: str = ""  # Audio device identifier for RTSP stream

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "enabled": self.enabled,
            "device_settings": self.device_settings,
            "stream_url": self.stream_url,
            "mjpeg_port": self.mjpeg_port,
            "resolution": self.resolution,
            "framerate": self.framerate,
            "rotation": self.rotation,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "saturation": self.saturation,
            "stream_resolution": self.stream_resolution,
            "stream_framerate": self.stream_framerate,
            "jpeg_quality": self.jpeg_quality,
            "stream_auth_enabled": self.stream_auth_enabled,
            "motion_detection_enabled": self.motion_detection_enabled,
            "motion_threshold": self.motion_threshold,
            "motion_frames": self.motion_frames,
            "record_movies": self.record_movies,
            "record_stills": self.record_stills,
            "pre_capture": self.pre_capture,
            "post_capture": self.post_capture,
            "overlay_left_text": self.overlay_left_text,
            "overlay_left_custom": self.overlay_left_custom,
            "overlay_right_text": self.overlay_right_text,
            "overlay_right_custom": self.overlay_right_custom,
            "overlay_text_scale": self.overlay_text_scale,
            "stream_source": self.stream_source,
            "motion_stream_port": self.motion_stream_port,
            "rtsp_enabled": self.rtsp_enabled,
            "rtsp_audio_device": self.rtsp_audio_device,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraConfig":
        return cls(
            identifier=data.get("identifier", "1"),
            name=data.get("name", "Camera"),
            enabled=data.get("enabled", True),
            device_settings=data.get("device_settings", {}),
            stream_url=data.get("stream_url", ""),
            mjpeg_port=data.get("mjpeg_port", 8081),
            resolution=data.get("resolution", "1280x720"),
            framerate=data.get("framerate", 15),
            rotation=data.get("rotation", 0),
            brightness=data.get("brightness", 0),
            contrast=data.get("contrast", 0),
            saturation=data.get("saturation", 0),
            stream_resolution=data.get("stream_resolution", data.get("resolution", "1280x720")),
            stream_framerate=data.get("stream_framerate", data.get("framerate", 15)),
            jpeg_quality=data.get("jpeg_quality", 80),
            motion_detection_enabled=data.get("motion_detection_enabled", True),
            motion_threshold=data.get("motion_threshold", 1500),
            motion_frames=data.get("motion_frames", 1),
            record_movies=data.get("record_movies", True),
            record_stills=data.get("record_stills", False),
            pre_capture=data.get("pre_capture", 0),
            post_capture=data.get("post_capture", 0),
            overlay_left_text=data.get("overlay_left_text", "disabled"),
            overlay_left_custom=data.get("overlay_left_custom", ""),
            overlay_right_text=data.get("overlay_right_text", "timestamp"),
            overlay_right_custom=data.get("overlay_right_custom", ""),
            overlay_text_scale=data.get("overlay_text_scale", 3),
            stream_auth_enabled=data.get("stream_auth_enabled", False),
            stream_source=data.get("stream_source", "auto"),
            motion_stream_port=data.get("motion_stream_port", 8081),
            rtsp_enabled=data.get("rtsp_enabled", False),
            rtsp_audio_device=data.get("rtsp_audio_device", ""),
        )


@dataclass
class AudioConfig:
    """Configuration for an audio input device."""
    identifier: str
    name: str
    enabled: bool = True
    device_id: str = ""  # ALSA device (hw:0,0) or Windows device name
    device_settings: Dict[str, str] = field(default_factory=dict)
    # Audio input settings
    sample_rate: int = 48000
    channels: int = 2
    bit_depth: int = 16
    volume: int = 100  # 0-100%
    # Noise reduction
    noise_reduction: bool = False
    noise_threshold: int = 50  # 0-100
    # Audio format settings for streaming
    codec: str = "aac"  # aac, opus, pcm
    bitrate: int = 128  # kbps for lossy codecs
    # Association with camera (optional)
    linked_camera_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "enabled": self.enabled,
            "device_id": self.device_id,
            "device_settings": self.device_settings,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "volume": self.volume,
            "noise_reduction": self.noise_reduction,
            "noise_threshold": self.noise_threshold,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "linked_camera_id": self.linked_camera_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioConfig":
        return cls(
            identifier=data.get("identifier", "1"),
            name=data.get("name", "Audio Input"),
            enabled=data.get("enabled", True),
            device_id=data.get("device_id", ""),
            device_settings=data.get("device_settings", {}),
            sample_rate=data.get("sample_rate", 48000),
            channels=data.get("channels", 2),
            bit_depth=data.get("bit_depth", 16),
            volume=data.get("volume", 100),
            noise_reduction=data.get("noise_reduction", False),
            noise_threshold=data.get("noise_threshold", 50),
            codec=data.get("codec", "aac"),
            bitrate=data.get("bitrate", 128),
            linked_camera_id=data.get("linked_camera_id", ""),
        )


class ConfigStore:
    """Configuration store with JSON file persistence. Cameras and audio devices have individual config files."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._cameras_dir = CAMERAS_CONFIG_DIR
        self._audio_dir = AUDIO_CONFIG_DIR
        self._dirty = False
        
        # Default values
        self.hostname = "motion-frontend-dev"
        self._theme = "dark"
        # Note: frontend_version is now a property that reads dynamically from CHANGELOG.md
        self._motion_version: Optional[str] = None
        self._update_available: Optional[str] = None
        self._cameras: Dict[str, CameraConfig] = {}
        self._audio_devices: Dict[str, AudioConfig] = {}
        self._logging_level = "INFO"
        self._log_to_file = True
        self._log_reset_on_start = False
        
        # Audio filter patterns (hide matching devices)
        self._audio_filter_patterns: List[str] = [
            r"hdmi",           # HDMI audio outputs
            r"spdif",          # S/PDIF outputs
            r"loopback",       # Loopback devices
        ]
        
        # Network config
        self._wifi_ssid = ""
        self._wifi_password = ""
        self._wifi_fallback_ssid = ""
        self._wifi_fallback_password = ""
        self._wifi_interface = "wlan0"
        self._ip_mode = "dhcp"
        self._static_ip = ""
        self._static_gateway = ""
        self._static_dns = ""
        
        # Display settings
        self._language = "fr"
        self._preview_count = 4
        self._preview_quality = "medium"
        
        # Admin/User credentials
        self._admin_username = "admin"
        self._admin_password = ""
        self._user_username = "user"
        self._user_password = ""
        
        # Camera detection filter patterns (hide matching devices)
        self._camera_filter_patterns: List[str] = [
            r"bcm2835-isp",      # Raspberry Pi ISP (not a real camera)
            r"unicam",           # Raspberry Pi CSI internal
            r"rp1-cfe",          # Raspberry Pi 5 CSI internal
        ]
        
        # Meeting API configuration
        self._meeting_server_url = "https://meeting.ygsoft.fr"
        self._meeting_device_key = ""
        self._meeting_token_code = ""
        self._meeting_heartbeat_interval = 60  # seconds
        
        # Load existing config or create defaults
        self._load_config()
        self._load_all_cameras()
        self._load_all_audio_devices()

    def _get_config_dict(self) -> Dict[str, Any]:
        """Serialize current main configuration to dictionary (without cameras/audio)."""
        return {
            "version": "2.1",
            "hostname": self.hostname,
            "theme": self._theme,
            "language": self._language,
            "logging_level": self._logging_level,
            "log_to_file": self._log_to_file,
            "log_reset_on_start": self._log_reset_on_start,
            "display": {
                "preview_count": self._preview_count,
                "preview_quality": self._preview_quality,
            },
            "network": {
                "wifi_ssid": self._wifi_ssid,
                "wifi_password": self._wifi_password,
                "wifi_fallback_ssid": self._wifi_fallback_ssid,
                "wifi_fallback_password": self._wifi_fallback_password,
                "wifi_interface": self._wifi_interface,
                "ip_mode": self._ip_mode,
                "static_ip": self._static_ip,
                "static_gateway": self._static_gateway,
                "static_dns": self._static_dns,
            },
            "auth": {
                "admin_username": self._admin_username,
                "admin_password": self._admin_password,
                "user_username": self._user_username,
                "user_password": self._user_password,
            },
            "camera_filter_patterns": self._camera_filter_patterns,
            "audio_filter_patterns": self._audio_filter_patterns,
            "meeting": {
                "server_url": self._meeting_server_url,
                "device_key": self._meeting_device_key,
                "token_code": self._meeting_token_code,
                "heartbeat_interval": self._meeting_heartbeat_interval,
            },
            # No cameras here - they have their own files
        }

    def _apply_config_dict(self, data: Dict[str, Any]) -> None:
        """Apply configuration from dictionary (main config only, no cameras)."""
        self.hostname = data.get("hostname", self.hostname)
        self._theme = data.get("theme", self._theme)
        self._language = data.get("language", self._language)
        self._logging_level = data.get("logging_level", self._logging_level)
        self._log_to_file = data.get("log_to_file", self._log_to_file)
        self._log_reset_on_start = data.get("log_reset_on_start", self._log_reset_on_start)
        
        display = data.get("display", {})
        self._preview_count = display.get("preview_count", self._preview_count)
        self._preview_quality = display.get("preview_quality", self._preview_quality)
        
        network = data.get("network", {})
        self._wifi_ssid = network.get("wifi_ssid", self._wifi_ssid)
        self._wifi_password = network.get("wifi_password", self._wifi_password)
        self._wifi_fallback_ssid = network.get("wifi_fallback_ssid", self._wifi_fallback_ssid)
        self._wifi_fallback_password = network.get("wifi_fallback_password", self._wifi_fallback_password)
        self._wifi_interface = network.get("wifi_interface", self._wifi_interface)
        self._ip_mode = network.get("ip_mode", self._ip_mode)
        self._static_ip = network.get("static_ip", self._static_ip)
        self._static_gateway = network.get("static_gateway", self._static_gateway)
        self._static_dns = network.get("static_dns", self._static_dns)
        
        auth = data.get("auth", {})
        self._admin_username = auth.get("admin_username", self._admin_username)
        self._admin_password = auth.get("admin_password", self._admin_password)
        self._user_username = auth.get("user_username", self._user_username)
        self._user_password = auth.get("user_password", self._user_password)
        
        # Camera filter patterns
        if "camera_filter_patterns" in data:
            self._camera_filter_patterns = data["camera_filter_patterns"]
        
        # Audio filter patterns
        if "audio_filter_patterns" in data:
            self._audio_filter_patterns = data["audio_filter_patterns"]
        
        # Meeting configuration
        meeting = data.get("meeting", {})
        self._meeting_server_url = meeting.get("server_url", self._meeting_server_url)
        self._meeting_device_key = meeting.get("device_key", self._meeting_device_key)
        self._meeting_token_code = meeting.get("token_code", self._meeting_token_code)
        self._meeting_heartbeat_interval = meeting.get("heartbeat_interval", self._meeting_heartbeat_interval)
        
        # Migration: if old config has cameras, migrate them to individual files
        cameras_data = data.get("cameras", {})
        if cameras_data:
            logger.info("Migrating %d cameras to individual config files", len(cameras_data))
            for cam_id, cam_data in cameras_data.items():
                cam = CameraConfig.from_dict(cam_data)
                self._cameras[cam_id] = cam
                self._save_camera_config(cam_id)
            # Save main config without cameras
            self._save_config()

    def _load_config(self) -> None:
        """Load main configuration from file, create with defaults if not exists."""
        try:
            if self._config_path.exists():
                with self._config_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self._apply_config_dict(data)
                logger.info("Configuration loaded from %s", self._config_path)
            else:
                self._save_config()
                logger.info("Created default configuration at %s", self._config_path)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in config file %s: %s", self._config_path, e)
        except Exception as e:
            logger.warning("Could not load config from %s: %s", self._config_path, e)

    def _load_all_cameras(self) -> None:
        """Load all camera configurations from individual files."""
        self._cameras_dir.mkdir(parents=True, exist_ok=True)
        for cam_file in self._cameras_dir.glob("*.json"):
            try:
                with cam_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                cam = CameraConfig.from_dict(data)
                self._cameras[cam.identifier] = cam
                logger.debug("Loaded camera config: %s", cam_file.name)
            except Exception as e:
                logger.error("Failed to load camera config %s: %s", cam_file, e)
        logger.info("Loaded %d camera configurations", len(self._cameras))

    def _load_all_audio_devices(self) -> None:
        """Load all audio device configurations from individual files."""
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        for audio_file in self._audio_dir.glob("*.json"):
            try:
                with audio_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                audio = AudioConfig.from_dict(data)
                self._audio_devices[audio.identifier] = audio
                logger.debug("Loaded audio config: %s", audio_file.name)
            except Exception as e:
                logger.error("Failed to load audio config %s: %s", audio_file, e)
        logger.info("Loaded %d audio device configurations", len(self._audio_devices))

    def _save_config(self) -> bool:
        """Save main configuration to file (without cameras)."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with self._config_path.open("w", encoding="utf-8") as f:
                json.dump(self._get_config_dict(), f, indent=2, ensure_ascii=False)
            self._dirty = False
            logger.info("Configuration saved to %s", self._config_path)
            return True
        except Exception as e:
            logger.error("Failed to save configuration to %s: %s", self._config_path, e)
            return False

    def _save_camera_config(self, camera_id: str) -> bool:
        """Save a single camera configuration to its own file."""
        camera = self._cameras.get(camera_id)
        if not camera:
            return False
        try:
            self._cameras_dir.mkdir(parents=True, exist_ok=True)
            cam_path = self._cameras_dir / f"{camera_id}.json"
            with cam_path.open("w", encoding="utf-8") as f:
                json.dump(camera.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info("Camera config saved to %s", cam_path)
            return True
        except Exception as e:
            logger.error("Failed to save camera config %s: %s", camera_id, e)
            return False

    def _delete_camera_config_file(self, camera_id: str) -> bool:
        """Delete a camera configuration file."""
        cam_path = self._cameras_dir / f"{camera_id}.json"
        try:
            if cam_path.exists():
                cam_path.unlink()
                logger.info("Deleted camera config file: %s", cam_path)
            return True
        except Exception as e:
            logger.error("Failed to delete camera config %s: %s", camera_id, e)
            return False

    def _save_audio_config(self, audio_id: str) -> bool:
        """Save a single audio device configuration to its own file."""
        audio = self._audio_devices.get(audio_id)
        if not audio:
            return False
        try:
            self._audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = self._audio_dir / f"{audio_id}.json"
            with audio_path.open("w", encoding="utf-8") as f:
                json.dump(audio.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info("Audio config saved to %s", audio_path)
            return True
        except Exception as e:
            logger.error("Failed to save audio config %s: %s", audio_id, e)
            return False

    def _delete_audio_config_file(self, audio_id: str) -> bool:
        """Delete an audio device configuration file."""
        audio_path = self._audio_dir / f"{audio_id}.json"
        try:
            if audio_path.exists():
                audio_path.unlink()
                logger.info("Deleted audio config file: %s", audio_path)
            return True
        except Exception as e:
            logger.error("Failed to delete audio config %s: %s", audio_id, e)
            return False

    def get_hostname(self) -> str:
        """Get hostname. If default, returns devicekey in lowercase if available."""
        if self.hostname == "motion-frontend-dev" and self._meeting_device_key:
            return self._meeting_device_key.lower()
        return self.hostname

    def get_effective_hostname(self) -> str:
        """Get the effective hostname for display in settings."""
        return self.get_hostname()

    def get_theme(self) -> str:
        return self._theme

    def set_theme(self, theme: str) -> None:
        self._theme = theme if theme in ("dark", "light") else "dark"
        self._dirty = True

    def get_main_config(self) -> Dict[str, List[Dict[str, Any]]]:
        # Get system versions dynamically
        sys_versions = system_info.get_system_versions()
        motion_status = sys_versions.motion_version or "Non installé"
        ffmpeg_status = sys_versions.ffmpeg_version or "Non installé"
        
        # Build update status - source updates take priority
        update_status = "À jour"
        if self._update_available:
            update_status = f"Nouvelle version disponible : {self._update_available}"

        # Effective hostname (devicekey in lowercase if default)
        effective_hostname = self.get_effective_hostname()

        return {
            "general": [
                {"id": "frontendVersion", "label": "Version Frontend", "type": "str", "value": self.frontend_version, "readonly": True},
                {"id": "motionVersion", "label": "Version Motion", "type": "str", "value": motion_status, "readonly": True},
                {"id": "ffmpegVersion", "label": "Version FFmpeg", "type": "str", "value": ffmpeg_status, "readonly": True},
                {"id": "updateStatus", "label": "Mise à jour", "type": "str", "value": update_status, "readonly": True},
                {"id": "separator1", "type": "separator", "label": "Système"},
                {"id": "hostname", "label": "Nom d'hôte", "type": "str", "value": effective_hostname},
                {"id": "restartService", "label": "Service", "type": "html", "html": "<button class='button button-warning restart-service-btn' id='restartServiceBtn'>Redémarrer le service</button>"},
                {"id": "language", "label": "Langue", "type": "choices", "choices": [
                    {"value": "fr", "label": "Français"},
                    {"value": "en", "label": "English"},
                    {"value": "de", "label": "Deutsch"},
                    {"value": "es", "label": "Español"},
                    {"value": "it", "label": "Italiano"},
                ], "value": self._language},
                {"id": "separatorLogging", "type": "separator", "label": "Journalisation"},
                {"id": "logLevel", "label": "Niveau de log", "type": "choices", "choices": [
                    {"value": "DEBUG", "label": "DEBUG (très verbeux)"},
                    {"value": "INFO", "label": "INFO (standard)"},
                    {"value": "WARNING", "label": "WARNING (avertissements)"},
                    {"value": "ERROR", "label": "ERROR (erreurs uniquement)"},
                    {"value": "CRITICAL", "label": "CRITICAL (critique)"},
                ], "value": self._logging_level},
                {"id": "logToFile", "label": "Enregistrer dans un fichier", "type": "bool", "value": self._log_to_file},
                {"id": "logResetOnStart", "label": "Effacer le log au démarrage", "type": "bool", "value": self._log_reset_on_start},
                {"id": "downloadLog", "label": "Télécharger", "type": "html", "html": "<button class='button download-log-btn' id='downloadLogBtn'>📥 Télécharger le log</button>"},
                {"id": "separatorAdmin", "type": "separator", "label": "Compte administrateur"},
                {"id": "adminUsername", "label": "Login admin", "type": "str", "value": "admin"},
                {"id": "adminPassword", "label": "Mot de passe admin", "type": "pwd", "value": "", "placeholder": "Nouveau mot de passe"},
                {"id": "separatorUser", "type": "separator", "label": "Compte utilisateur"},
                {"id": "userUsername", "label": "Login utilisateur", "type": "str", "value": "user"},
                {"id": "userPassword", "label": "Mot de passe utilisateur", "type": "pwd", "value": "", "placeholder": "Nouveau mot de passe"},
            ],
            "network_manager": [
                {"id": "wifiSeparator", "type": "separator", "label": "Wi-Fi principal"},
                {"id": "wifiSsid", "label": "SSID", "type": "str", "value": self._wifi_ssid, "placeholder": "Nom du réseau"},
                {"id": "wifiPassword", "label": "Mot de passe", "type": "pwd", "value": self._wifi_password},
                {"id": "wifiFallbackSeparator", "type": "separator", "label": "Wi-Fi de secours"},
                {"id": "wifiFallbackSsid", "label": "SSID secours", "type": "str", "value": self._wifi_fallback_ssid, "placeholder": "Réseau de secours"},
                {"id": "wifiFallbackPassword", "label": "Mot de passe", "type": "pwd", "value": self._wifi_fallback_password},
                {"id": "wifiInterface", "label": "Interface Wi-Fi", "type": "choices", "choices": [
                    {"value": "wlan0", "label": "wlan0 (intégré)"},
                    {"value": "wlan1", "label": "wlan1 (dongle USB)"},
                ], "value": self._wifi_interface},
                {"id": "ipSeparator", "type": "separator", "label": "Configuration IP"},
                {"id": "ipMode", "label": "Mode IP", "type": "choices", "choices": [
                    {"value": "dhcp", "label": "DHCP (automatique)"},
                    {"value": "static", "label": "IP fixe"},
                ], "value": self._ip_mode},
                {"id": "staticIp", "label": "Adresse IP", "type": "str", "value": self._static_ip, "placeholder": "192.168.1.100", "depends": "ipMode:static"},
                {"id": "staticGateway", "label": "Passerelle", "type": "str", "value": self._static_gateway, "placeholder": "192.168.1.1", "depends": "ipMode:static"},
                {"id": "staticDns", "label": "Serveur DNS", "type": "str", "value": self._static_dns, "placeholder": "8.8.8.8", "depends": "ipMode:static"},
            ],
            "backup": [
                {"id": "backupNow", "label": "Sauvegarder", "type": "html", "html": "<button class='button backup-action' id='backupActionBtn'>Créer une sauvegarde</button>"},
                {"id": "restoreNow", "label": "Restaurer", "type": "html", "html": "<button class='button restore-action' id='restoreActionBtn'>Restaurer une sauvegarde</button>"},
            ],
            "display_settings": [
                {"id": "previewCount", "label": "Nombre de previews", "type": "choices", "choices": [
                    {"value": "1", "label": "1 (Simple)"},
                    {"value": "2", "label": "2 (Double)"},
                    {"value": "4", "label": "4 (Quad)"},
                    {"value": "8", "label": "8"},
                    {"value": "16", "label": "16"},
                    {"value": "32", "label": "32"},
                ], "value": str(self._preview_count)},
                {"id": "previewQuality", "label": "Qualité des previews", "type": "choices", "choices": [
                    {"value": "low", "label": "Basse (rapide, peu de mémoire)"},
                    {"value": "medium", "label": "Moyenne"},
                    {"value": "high", "label": "Haute (plus de détails)"},
                ], "value": self._preview_quality},
            ],
            "meeting": [
                {"id": "meetingDeviceKey", "label": "Device Key", "type": "str", "value": self._meeting_device_key, "placeholder": "ABCDEF123456"},
                {"id": "meetingTokenCode", "label": "Token Code", "type": "pwd", "value": self._meeting_token_code, "placeholder": "Token d'authentification"},
                {"id": "meetingHeartbeatInterval", "label": "Intervalle heartbeat (sec)", "type": "number", "value": self._meeting_heartbeat_interval, "min": 10, "max": 3600},
                {"id": "meetingStatus", "label": "État", "type": "html", "html": "<span id='meetingStatusLabel' class='meeting-status'>--</span>"},
            ],
        }

    def get_cameras(self) -> List[Dict[str, Any]]:
        cameras = []
        for cam in self._cameras.values():
            camera_data = {
                "id": cam.identifier,
                "name": cam.name,
                "enabled": cam.enabled,
                "rtsp_enabled": cam.rtsp_enabled,
            }
            # Add HLS URL if RTSP is enabled (MediaMTX serves HLS on port 8888)
            if cam.rtsp_enabled:
                camera_data["hls_url"] = f"/hls/cam{cam.identifier}/index.m3u8"
                camera_data["rtsp_port"] = 8554
            cameras.append(camera_data)
        return cameras

    def get_camera(self, camera_id: str) -> Optional[CameraConfig]:
        return self._cameras.get(camera_id)

    def _get_camera_image_section(self, cam: CameraConfig) -> List[Dict[str, Any]]:
        """Get camera image controls section based on platform.
        
        Windows: Show historical brightness/contrast/saturation sliders plus V4L2/DirectShow detection.
        Linux: Only show V4L2 detection button and container for detected controls.
        """
        import platform
        is_linux = platform.system().lower() == "linux"
        
        if is_linux:
            # Linux: only show detection button and container for V4L2 controls
            return [
                {"id": "detectControls", "label": "", "type": "html", "html": '<button type="button" id="detectCameraControlsBtn" class="btn-detect">🔍 Détecter les contrôles V4L2</button><div class="detect-hint">Détecte les contrôles disponibles sur le périphérique vidéo</div>'},
                {"id": "cameraControls", "label": "", "type": "html", "html": '<div id="cameraControlsContainer" class="camera-controls-list"></div>'},
            ]
        else:
            # Windows: show historical sliders plus DirectShow detection
            return [
                {"id": "brightness", "label": "Luminosité", "type": "range", "value": cam.brightness, "min": -100, "max": 100},
                {"id": "contrast", "label": "Contraste", "type": "range", "value": cam.contrast, "min": -100, "max": 100},
                {"id": "saturation", "label": "Saturation", "type": "range", "value": cam.saturation, "min": -100, "max": 100},
                {"id": "imageSeparator", "label": "Contrôles avancés", "type": "separator"},
                {"id": "detectControls", "label": "", "type": "html", "html": '<button type="button" id="detectCameraControlsBtn" class="btn-detect">🔍 Détecter les contrôles</button><div class="detect-hint">Détecte les contrôles disponibles sur le périphérique (DirectShow)</div>'},
                {"id": "cameraControls", "label": "", "type": "html", "html": '<div id="cameraControlsContainer" class="camera-controls-list"></div>'},
            ]

    def _get_audio_device_choices(self) -> List[Dict[str, str]]:
        """Get list of audio devices as choices for dropdown."""
        choices = [{"value": "", "label": "Aucun (vidéo uniquement)"}]
        for audio in self._audio_devices.values():
            if audio.enabled:
                choices.append({
                    "value": audio.identifier,
                    "label": f"{audio.name} ({audio.device_id})"
                })
        return choices

    def _get_stream_source_choices(self) -> List[Dict[str, str]]:
        """Get stream source choices based on Motion availability."""
        choices = [
            {"value": "auto", "label": "Auto (Motion si disponible)"},
            {"value": "internal", "label": "Serveur MJPEG intégré"},
        ]
        
        # Check if Motion is installed
        sys_versions = system_info.get_system_versions()
        if sys_versions.motion_version:
            choices.append({
                "value": "motion", 
                "label": f"Motion ({sys_versions.motion_version})"
            })
        
        return choices

    def _get_rtsp_url_html(self, cam: CameraConfig, camera_id: str) -> str:
        """Generate HTML for RTSP URL display."""
        server_ip = _get_local_ip()
        rtsp_port = 8554 + int(camera_id) - 1
        rtsp_path = f"/cam{camera_id}"
        rtsp_url = f"rtsp://{server_ip}:{rtsp_port}{rtsp_path}"
        
        # Show the URL whether RTSP is enabled or not (informational)
        enabled_class = "rtsp-enabled" if cam.rtsp_enabled else "rtsp-disabled"
        status_hint = "" if cam.rtsp_enabled else " <small class='text-muted'>(activer RTSP pour utiliser)</small>"
        
        return f"""<code id='rtspUrlDisplay_{camera_id}' class='stream-url {enabled_class}' 
            data-camera-id='{camera_id}' 
            data-rtsp-port='{rtsp_port}' 
            data-rtsp-path='{rtsp_path}'
            data-server-ip='{server_ip}'>{rtsp_url}</code> 
            <button type='button' class='btn-copy' onclick="navigator.clipboard.writeText('{rtsp_url}'); motionFrontendUI.showToast('URL RTSP copiée', 'success');" title='Copier'>📋</button>{status_hint}"""
    def _get_stream_url_html(self, cam: CameraConfig, camera_id: str) -> str:
        """Generate HTML for stream URL display.
        
        URL depends on stream source:
        - Motion/Auto: Use proxy endpoint (http://IP:8765/stream/{camera_id}/)
          because Motion listens on localhost only
        - Internal: Use dedicated MJPEG port (http://IP:{mjpeg_port}/stream/)
          which is accessible directly
        """
        server_ip = _get_local_ip()
        server_port = _get_server_port()
        
        # Determine URL based on stream source
        if cam.stream_source == "internal":
            # Internal MJPEG server has dedicated port accessible from network
            stream_url = f"http://{server_ip}:{cam.mjpeg_port}/stream/"
            source_hint = "(serveur dédié)"
            data_attrs = f"data-mjpeg-port='{cam.mjpeg_port}'"
        else:
            # Motion or Auto: use proxy endpoint (Motion listens on localhost)
            stream_url = f"http://{server_ip}:{server_port}/stream/{camera_id}/"
            source_hint = "(proxy Motion)" if cam.stream_source == "motion" else "(auto/proxy)"
            data_attrs = f"data-server-port='{server_port}'"
        
        auth_hint = " 🔒" if cam.stream_auth_enabled else ""
        
        return f"""<code id='streamUrlDisplay' class='stream-url' 
            data-camera-id='{camera_id}' 
            data-stream-source='{cam.stream_source or "auto"}'
            {data_attrs}
            data-server-ip='{server_ip}'>{stream_url}</code> 
            <button type='button' class='btn-copy' onclick='copyStreamUrl()' title='Copier'>📋</button>
            <small class='stream-source-hint'>{source_hint}{auth_hint}</small>"""

    def get_camera_config(self, camera_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get camera configuration sections for the UI."""
        cam = self._cameras.get(camera_id)
        if not cam:
            return {}
        return {
            "camera_device": [
                {"id": "deviceName", "label": "Nom", "type": "str", "value": cam.name},
                {"id": "deviceUrl", "label": "Source vidéo", "type": "str", "value": cam.device_settings.get("device", ""), "placeholder": "rtsp://... ou /dev/video0"},
            ],
            "camera_video": [
                {"id": "resolution", "label": "Résolution capture", "type": "choices", "choices": [
                    {"value": "640x480", "label": "640x480 (VGA)"},
                    {"value": "1280x720", "label": "1280x720 (720p)"},
                    {"value": "1920x1080", "label": "1920x1080 (1080p)"},
                    {"value": "2560x1440", "label": "2560x1440 (2K)"},
                    {"value": "3840x2160", "label": "3840x2160 (4K)"},
                ], "value": cam.resolution},
                {"id": "detectResolutions", "label": "", "type": "html", "html": '<button type="button" id="detectResolutionsBtn" class="btn-detect" title="Détecter les résolutions disponibles">🔍 Détecter</button>'},
                {"id": "framerate", "label": "Images/sec capture", "type": "number", "value": cam.framerate, "min": 1, "max": 60},
                {"id": "rotation", "label": "Rotation", "type": "choices", "choices": [
                    {"value": "0", "label": "0°"},
                    {"value": "90", "label": "90°"},
                    {"value": "180", "label": "180°"},
                    {"value": "270", "label": "270°"},
                ], "value": str(cam.rotation)},
            ],
            "camera_image": self._get_camera_image_section(cam),
            "camera_streaming": [
                {"id": "streamEnabled", "label": "Streaming actif", "type": "bool", "value": cam.enabled},
                {"id": "streamSource", "label": "Source du stream", "type": "choices", "choices": self._get_stream_source_choices(), "value": cam.stream_source},
                {"id": "mjpegPort", "label": "Port MJPEG", "type": "number", "value": cam.mjpeg_port, "min": 1024, "max": 65535},
                {"id": "motionStreamPort", "label": "Port Motion (si externe)", "type": "number", "value": cam.motion_stream_port, "min": 1024, "max": 65535, "depends": "streamSource=motion"},
                {"id": "streamResolution", "label": "Résolution sortie", "type": "choices", "choices": [
                    {"value": "320x240", "label": "320x240 (QVGA)"},
                    {"value": "640x480", "label": "640x480 (VGA)"},
                    {"value": "1280x720", "label": "1280x720 (720p)"},
                    {"value": "1920x1080", "label": "1920x1080 (1080p)"},
                ], "value": cam.stream_resolution},
                {"id": "streamFramerate", "label": "Images/sec sortie", "type": "number", "value": cam.stream_framerate, "min": 1, "max": 30},
                {"id": "jpegQuality", "label": "Qualité JPEG (%)", "type": "range", "value": cam.jpeg_quality, "min": 10, "max": 100},
                {"id": "streamAuthEnabled", "label": "Authentification requise", "type": "bool", "value": cam.stream_auth_enabled},
                {"id": "streamUrl", "label": "URL du stream", "type": "html", "html": self._get_stream_url_html(cam, camera_id)},
            ],
            "camera_rtsp": [
                {"id": "rtspEnabled", "label": "Streaming RTSP actif", "type": "bool", "value": cam.rtsp_enabled},
                {"id": "rtspStatus", "label": "Statut", "type": "html", "html": f"""
                    <div class="rtsp-status-info" data-camera-id="{camera_id}">
                        <span id="rtspStatusBadge_{camera_id}" class="rtsp-status stopped">Arrêté</span>
                        <span id="rtspAudioBadge_{camera_id}" class="rtsp-audio-badge" style="display:none;"></span>
                        <div id="rtspUrlDisplay_{camera_id}" class="rtsp-url-display" style="display:none;"></div>
                        <div id="rtspError_{camera_id}" class="rtsp-error" style="display:none;"></div>
                    </div>
                """},
                {"id": "rtspUrl", "label": "URL RTSP", "type": "html", "html": self._get_rtsp_url_html(cam, camera_id)},
                {"id": "rtspAudioDevice", "label": "Périphérique audio", "type": "choices", "choices": self._get_audio_device_choices(), "value": cam.rtsp_audio_device},
                {"id": "rtspPort", "label": "Port RTSP", "type": "html", "html": f"<code>{8554 + int(camera_id) - 1}</code> <small>(calculé automatiquement)</small>"},
            ],
            "camera_overlay": [
                {"id": "overlayLeftText", "label": "Texte gauche", "type": "choices", "choices": [
                    {"value": "disabled", "label": "Désactivé"},
                    {"value": "camera_name", "label": "Nom de la caméra"},
                    {"value": "timestamp", "label": "Date/heure"},
                    {"value": "custom", "label": "Texte personnalisé"},
                    {"value": "capture_info", "label": "Infos capture"},
                ], "value": cam.overlay_left_text},
                {"id": "overlayLeftCustom", "label": "Texte personnalisé gauche", "type": "str", "value": cam.overlay_left_custom, "placeholder": "Entrez votre texte...", "depends": "overlayLeftText=custom"},
                {"id": "overlayRightText", "label": "Texte droite", "type": "choices", "choices": [
                    {"value": "disabled", "label": "Désactivé"},
                    {"value": "camera_name", "label": "Nom de la caméra"},
                    {"value": "timestamp", "label": "Date/heure"},
                    {"value": "custom", "label": "Texte personnalisé"},
                    {"value": "capture_info", "label": "Infos capture"},
                ], "value": cam.overlay_right_text},
                {"id": "overlayRightCustom", "label": "Texte personnalisé droite", "type": "str", "value": cam.overlay_right_custom, "placeholder": "Entrez votre texte...", "depends": "overlayRightText=custom"},
                {"id": "overlayTextScale", "label": "Taille du texte", "type": "range", "value": cam.overlay_text_scale, "min": 1, "max": 10},
            ],
            "camera_motion": [
                {"id": "motionEnabled", "label": "Détection mouvement", "type": "bool", "value": cam.motion_detection_enabled},
                {"id": "motionThreshold", "label": "Seuil détection", "type": "number", "value": cam.motion_threshold, "min": 1, "max": 100000, "depends": "motionEnabled"},
                {"id": "motionFrames", "label": "Images consécutives", "type": "number", "value": cam.motion_frames, "min": 1, "max": 100, "depends": "motionEnabled"},
            ],
            "camera_recording": [
                {"id": "recordMovies", "label": "Enregistrer vidéos", "type": "bool", "value": cam.record_movies},
                {"id": "recordStills", "label": "Enregistrer images", "type": "bool", "value": cam.record_stills},
                {"id": "preCapture", "label": "Pré-capture (sec)", "type": "number", "value": cam.pre_capture, "min": 0, "max": 60},
                {"id": "postCapture", "label": "Post-capture (sec)", "type": "number", "value": cam.post_capture, "min": 0, "max": 300},
            ],
        }

    def get_camera_config_sections(self, camera_id: str) -> List[Dict[str, Any]]:
        """Get camera configuration as sections list for template rendering."""
        config = self.get_camera_config(camera_id)
        if not config:
            return []
        
        sections = [
            {"slug": "camera_device", "title": "Périphérique", "configs": config.get("camera_device", [])},
            {"slug": "camera_video", "title": "Paramètres vidéo", "configs": config.get("camera_video", [])},
            {"slug": "camera_image", "title": "Image", "configs": config.get("camera_image", [])},
            {"slug": "camera_streaming", "title": "Streaming MJPEG", "configs": config.get("camera_streaming", [])},
            {"slug": "camera_rtsp", "title": "Streaming RTSP", "configs": config.get("camera_rtsp", [])},
            {"slug": "camera_overlay", "title": "Text Overlay", "configs": config.get("camera_overlay", [])},
            {"slug": "camera_motion", "title": "Détection de mouvement", "configs": config.get("camera_motion", [])},
            {"slug": "camera_recording", "title": "Enregistrement", "configs": config.get("camera_recording", [])},
        ]
        return [s for s in sections if s["configs"]]

    def save_main_config(self, payload: Dict[str, str]) -> Dict[str, str]:
        if "hostname" in payload:
            self.hostname = payload["hostname"]
        if "language" in payload:
            self._language = payload["language"]
        if "logLevel" in payload:
            new_level = payload["logLevel"].upper()
            if new_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                self._logging_level = new_level
                # Apply new log level immediately
                logging.getLogger().setLevel(getattr(logging, new_level))
                logger.info("Log level changed to %s", new_level)
        if "logToFile" in payload:
            self._log_to_file = payload["logToFile"] in (True, "true", "1", "on")
        if "logResetOnStart" in payload:
            self._log_reset_on_start = payload["logResetOnStart"] in (True, "true", "1", "on")
        if "previewCount" in payload:
            self._preview_count = int(payload["previewCount"])
        if "previewQuality" in payload:
            self._preview_quality = payload["previewQuality"]
        if "wifiSsid" in payload:
            self._wifi_ssid = payload["wifiSsid"]
        if "wifiPassword" in payload:
            self._wifi_password = payload["wifiPassword"]
        if "wifiFallbackSsid" in payload:
            self._wifi_fallback_ssid = payload["wifiFallbackSsid"]
        if "wifiFallbackPassword" in payload:
            self._wifi_fallback_password = payload["wifiFallbackPassword"]
        if "wifiInterface" in payload:
            self._wifi_interface = payload["wifiInterface"]
        if "ipMode" in payload:
            self._ip_mode = payload["ipMode"]
        if "staticIp" in payload:
            self._static_ip = payload["staticIp"]
        if "staticGateway" in payload:
            self._static_gateway = payload["staticGateway"]
        if "staticDns" in payload:
            self._static_dns = payload["staticDns"]
        
        # Meeting configuration (server_url is hardcoded)
        if "meetingDeviceKey" in payload:
            self._meeting_device_key = payload["meetingDeviceKey"]
        if "meetingTokenCode" in payload:
            self._meeting_token_code = payload["meetingTokenCode"]
        if "meetingHeartbeatInterval" in payload:
            self._meeting_heartbeat_interval = int(payload["meetingHeartbeatInterval"])
        
        # Handle user password changes via UserManager
        from .user_manager import get_user_manager
        user_manager = get_user_manager()
        
        if "adminPassword" in payload and payload["adminPassword"]:
            # Change admin password
            success, msg = user_manager.set_password("admin", payload["adminPassword"], must_change=False)
            if success:
                logger.info("Admin password updated via UI")
            else:
                logger.warning("Failed to update admin password: %s", msg)
        
        if "userPassword" in payload and payload["userPassword"]:
            # Change user password (user account is auto-created by UserManager)
            success, msg = user_manager.set_password("user", payload["userPassword"], must_change=False)
            if success:
                logger.info("User password updated via UI")
            else:
                logger.warning("Failed to update user password: %s", msg)
        
        self._dirty = True
        self._save_config()
        return {"status": "ok", "updated": list(payload.keys())}

    def save_camera_config(self, camera_id: str, payload: Dict[str, Any]) -> Dict[str, str]:
        """Update camera configuration and save to its individual file."""
        camera = self._cameras.get(camera_id)
        if not camera:
            raise KeyError(f"Camera {camera_id} not found")
        
        # Device settings
        if "deviceName" in payload:
            camera.name = payload["deviceName"]
        if "deviceUrl" in payload:
            new_device = payload["deviceUrl"]
            camera.device_settings["device"] = new_device
            # Auto-detect and store stable device path on Linux
            stable_path = find_stable_video_path(new_device)
            if stable_path:
                camera.device_settings["stable_device_path"] = stable_path
                logger.info("Auto-detected stable path for camera %s: %s -> %s", 
                           camera_id, new_device, stable_path)
            elif "stable_device_path" in camera.device_settings:
                # Clear old stable path if device changed but no new stable path found
                del camera.device_settings["stable_device_path"]
        
        # Video settings
        if "resolution" in payload:
            camera.resolution = payload["resolution"]
        if "framerate" in payload:
            camera.framerate = _safe_int(payload["framerate"], camera.framerate)
        if "rotation" in payload:
            camera.rotation = _safe_int(payload["rotation"], camera.rotation)
        
        # Image settings
        if "brightness" in payload:
            camera.brightness = _safe_int(payload["brightness"], camera.brightness)
        if "contrast" in payload:
            camera.contrast = _safe_int(payload["contrast"], camera.contrast)
        if "saturation" in payload:
            camera.saturation = _safe_int(payload["saturation"], camera.saturation)
        
        # Streaming
        if "streamEnabled" in payload:
            camera.enabled = payload["streamEnabled"] in (True, "true", "1", "on")
        if "streamSource" in payload:
            camera.stream_source = payload["streamSource"]
        if "motionStreamPort" in payload:
            camera.motion_stream_port = _safe_int(payload["motionStreamPort"], camera.motion_stream_port)
        if "streamAuthEnabled" in payload:
            camera.stream_auth_enabled = payload["streamAuthEnabled"] in (True, "true", "1", "on")
        if "mjpegPort" in payload:
            camera.mjpeg_port = _safe_int(payload["mjpegPort"], camera.mjpeg_port)
        if "streamResolution" in payload:
            camera.stream_resolution = payload["streamResolution"]
        if "streamFramerate" in payload:
            camera.stream_framerate = _safe_int(payload["streamFramerate"], camera.stream_framerate)
        if "jpegQuality" in payload:
            camera.jpeg_quality = _safe_int(payload["jpegQuality"], camera.jpeg_quality)
        
        # Motion detection
        if "motionEnabled" in payload:
            camera.motion_detection_enabled = payload["motionEnabled"] in (True, "true", "1", "on")
        if "motionThreshold" in payload:
            camera.motion_threshold = _safe_int(payload["motionThreshold"], camera.motion_threshold)
        if "motionFrames" in payload:
            camera.motion_frames = _safe_int(payload["motionFrames"], camera.motion_frames)
        
        # Recording
        if "recordMovies" in payload:
            camera.record_movies = payload["recordMovies"] in (True, "true", "1", "on")
        if "recordStills" in payload:
            camera.record_stills = payload["recordStills"] in (True, "true", "1", "on")
        if "preCapture" in payload:
            camera.pre_capture = _safe_int(payload["preCapture"], camera.pre_capture)
        if "postCapture" in payload:
            camera.post_capture = _safe_int(payload["postCapture"], camera.post_capture)
        
        # Text overlay
        if "overlayLeftText" in payload:
            camera.overlay_left_text = payload["overlayLeftText"]
        if "overlayLeftCustom" in payload:
            camera.overlay_left_custom = payload["overlayLeftCustom"]
        if "overlayRightText" in payload:
            camera.overlay_right_text = payload["overlayRightText"]
        if "overlayRightCustom" in payload:
            camera.overlay_right_custom = payload["overlayRightCustom"]
        if "overlayTextScale" in payload:
            camera.overlay_text_scale = _safe_int(payload["overlayTextScale"], camera.overlay_text_scale)
        
        # RTSP streaming
        if "rtspEnabled" in payload:
            camera.rtsp_enabled = payload["rtspEnabled"] in (True, "true", "1", "on")
        if "rtspAudioDevice" in payload:
            camera.rtsp_audio_device = payload["rtspAudioDevice"]
        
        # Save to individual file
        self._save_camera_config(camera_id)
        
        # Build response with warnings if needed
        response = {"status": "ok", "camera": camera_id}
        
        # Check if video parameters changed and Motion is running
        video_params_changed = any(k in payload for k in [
            "resolution", "framerate", "streamResolution", "streamFramerate", "jpegQuality"
        ])
        if video_params_changed:
            import platform
            if platform.system().lower() == "linux":
                from . import system_info
                if system_info.is_motion_running():
                    response["warning"] = (
                        "Les paramètres vidéo ont été sauvegardés. "
                        "Si Motion gère le flux, redémarrez-le pour appliquer les changements : "
                        "sudo systemctl restart motion"
                    )
        
        return response

    def add_camera(self, name: str = "", device_url: str = "") -> Dict[str, Any]:
        """Add a new camera with its own configuration file."""
        # Find next available ID
        existing_ids = [int(cid) for cid in self._cameras.keys() if cid.isdigit()]
        next_id = str(max(existing_ids, default=0) + 1)
        
        camera_name = name if name else f"Camera {next_id}"
        
        new_camera = CameraConfig(
            identifier=next_id,
            name=camera_name,
            enabled=True,
            device_settings={"device": device_url},
            stream_url="",
            mjpeg_port=8081 + int(next_id) - 1,
            resolution="1280x720",
            framerate=15,
        )
        self._cameras[next_id] = new_camera
        
        # Save to individual file
        self._save_camera_config(next_id)
        
        logger.info("Added camera %s: %s", next_id, camera_name)
        return {
            "status": "ok",
            "camera": {
                "id": next_id,
                "name": camera_name,
                "enabled": True,
            }
        }

    def remove_camera(self, camera_id: str) -> Dict[str, str]:
        """Remove a camera and delete its configuration file."""
        if camera_id not in self._cameras:
            raise KeyError(f"Camera {camera_id} not found")
        
        del self._cameras[camera_id]
        self._delete_camera_config_file(camera_id)
        
        logger.info("Removed camera %s", camera_id)
        return {"status": "ok", "removed": camera_id}

    def get_version_payload(self, frontend_version: str, commit: str) -> Dict[str, str]:
        return {
            "frontend": frontend_version,
            "backend": "0.1.0",
            "commit": commit,
            "build_date": datetime.utcnow().isoformat() + "Z",
        }

    def get_logging_level(self) -> str:
        return self._logging_level

    def get_log_to_file(self) -> bool:
        return self._log_to_file

    def get_log_reset_on_start(self) -> bool:
        return self._log_reset_on_start

    def set_logging_level(self, level: str) -> None:
        self._logging_level = level.upper()
        self._dirty = True
        self._save_config()

    def save_now(self) -> bool:
        """Force save configuration to disk."""
        return self._save_config()

    def reload(self) -> None:
        """Reload configuration from disk."""
        self._load_config()

    # Camera filter patterns methods
    def get_camera_filter_patterns(self) -> List[str]:
        """Get the list of camera filter patterns."""
        return self._camera_filter_patterns.copy()

    def set_camera_filter_patterns(self, patterns: List[str]) -> None:
        """Set the camera filter patterns and save config."""
        self._camera_filter_patterns = patterns
        self._save_config()
        logger.info("Updated camera filter patterns: %s", patterns)

    def add_camera_filter_pattern(self, pattern: str) -> None:
        """Add a new filter pattern."""
        if pattern and pattern not in self._camera_filter_patterns:
            self._camera_filter_patterns.append(pattern)
            self._save_config()
            logger.info("Added camera filter pattern: %s", pattern)

    def remove_camera_filter_pattern(self, pattern: str) -> None:
        """Remove a filter pattern."""
        if pattern in self._camera_filter_patterns:
            self._camera_filter_patterns.remove(pattern)
            self._save_config()
            logger.info("Removed camera filter pattern: %s", pattern)

    # Audio filter patterns methods
    def get_audio_filter_patterns(self) -> List[str]:
        """Get the list of audio filter patterns."""
        return self._audio_filter_patterns.copy()

    def set_audio_filter_patterns(self, patterns: List[str]) -> None:
        """Set the audio filter patterns and save config."""
        self._audio_filter_patterns = patterns
        self._save_config()
        logger.info("Updated audio filter patterns: %s", patterns)

    def add_audio_filter_pattern(self, pattern: str) -> None:
        """Add a new audio filter pattern."""
        if pattern and pattern not in self._audio_filter_patterns:
            self._audio_filter_patterns.append(pattern)
            self._save_config()
            logger.info("Added audio filter pattern: %s", pattern)

    def remove_audio_filter_pattern(self, pattern: str) -> None:
        """Remove an audio filter pattern."""
        if pattern in self._audio_filter_patterns:
            self._audio_filter_patterns.remove(pattern)
            self._save_config()
            logger.info("Removed audio filter pattern: %s", pattern)

    # Audio device management methods
    def get_audio_devices(self) -> List[Dict[str, Any]]:
        """Get list of configured audio devices."""
        return [
            {"id": audio.identifier, "name": audio.name, "enabled": audio.enabled}
            for audio in self._audio_devices.values()
        ]

    def get_audio_device(self, audio_id: str) -> Optional[AudioConfig]:
        """Get a specific audio device configuration."""
        return self._audio_devices.get(audio_id)

    def get_audio_config(self, audio_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get audio device configuration sections for the UI."""
        audio = self._audio_devices.get(audio_id)
        if not audio:
            return {}
        
        # Get list of available cameras for linking
        camera_choices = [{"value": "", "label": "Aucune"}]
        camera_choices.extend([
            {"value": cam.identifier, "label": cam.name}
            for cam in self._cameras.values()
        ])
        
        return {
            "audio_device": [
                {"id": "audioDeviceName", "label": "Nom", "type": "str", "value": audio.name},
                {"id": "audioDeviceId", "label": "Périphérique", "type": "str", "value": audio.device_id, "readonly": True},
            ],
            "audio_input": [
                {"id": "audioEnabled", "label": "Audio actif", "type": "bool", "value": audio.enabled},
                {"id": "audioSampleRate", "label": "Fréquence d'échantillonnage", "type": "choices", "choices": [
                    {"value": "8000", "label": "8 kHz (téléphone)"},
                    {"value": "16000", "label": "16 kHz (voix)"},
                    {"value": "22050", "label": "22.05 kHz"},
                    {"value": "44100", "label": "44.1 kHz (CD)"},
                    {"value": "48000", "label": "48 kHz (pro)"},
                ], "value": str(audio.sample_rate)},
                {"id": "audioChannels", "label": "Canaux", "type": "choices", "choices": [
                    {"value": "1", "label": "Mono"},
                    {"value": "2", "label": "Stéréo"},
                ], "value": str(audio.channels)},
                {"id": "audioBitDepth", "label": "Résolution", "type": "choices", "choices": [
                    {"value": "16", "label": "16 bits"},
                    {"value": "24", "label": "24 bits"},
                    {"value": "32", "label": "32 bits"},
                ], "value": str(audio.bit_depth)},
                {"id": "audioVolume", "label": "Volume (%)", "type": "range", "value": audio.volume, "min": 0, "max": 100},
            ],
            "audio_processing": [
                {"id": "audioNoiseReduction", "label": "Réduction de bruit", "type": "bool", "value": audio.noise_reduction},
                {"id": "audioNoiseThreshold", "label": "Seuil de bruit", "type": "range", "value": audio.noise_threshold, "min": 0, "max": 100, "depends": "audioNoiseReduction"},
            ],
            "audio_encoding": [
                {"id": "audioCodec", "label": "Codec", "type": "choices", "choices": [
                    {"value": "aac", "label": "AAC (recommandé)"},
                    {"value": "opus", "label": "Opus (basse latence)"},
                    {"value": "pcm", "label": "PCM (non compressé)"},
                ], "value": audio.codec},
                {"id": "audioBitrate", "label": "Bitrate (kbps)", "type": "choices", "choices": [
                    {"value": "64", "label": "64 kbps (voix)"},
                    {"value": "96", "label": "96 kbps"},
                    {"value": "128", "label": "128 kbps (standard)"},
                    {"value": "192", "label": "192 kbps"},
                    {"value": "256", "label": "256 kbps (haute qualité)"},
                ], "value": str(audio.bitrate), "depends": "!audioCodec=pcm"},
            ],
            "audio_association": [
                {"id": "audioLinkedCamera", "label": "Caméra associée", "type": "choices", "choices": camera_choices, "value": audio.linked_camera_id},
            ],
        }

    def get_audio_config_sections(self, audio_id: str) -> List[Dict[str, Any]]:
        """Get audio configuration as sections list for template rendering."""
        config = self.get_audio_config(audio_id)
        if not config:
            return []
        
        sections = [
            {"slug": "audio_device", "title": "Périphérique audio", "configs": config.get("audio_device", [])},
            {"slug": "audio_input", "title": "Paramètres d'entrée", "configs": config.get("audio_input", [])},
            {"slug": "audio_processing", "title": "Traitement audio", "configs": config.get("audio_processing", [])},
            {"slug": "audio_encoding", "title": "Encodage", "configs": config.get("audio_encoding", [])},
            {"slug": "audio_association", "title": "Association caméra", "configs": config.get("audio_association", [])},
        ]
        return [s for s in sections if s["configs"]]

    def save_audio_config(self, audio_id: str, payload: Dict[str, Any]) -> Dict[str, str]:
        """Update audio device configuration and save to its individual file."""
        audio = self._audio_devices.get(audio_id)
        if not audio:
            raise KeyError(f"Audio device {audio_id} not found")
        
        # Device settings
        if "audioDeviceName" in payload:
            audio.name = payload["audioDeviceName"]
        
        # Input settings
        if "audioEnabled" in payload:
            audio.enabled = payload["audioEnabled"] in (True, "true", "1", "on")
        if "audioSampleRate" in payload:
            audio.sample_rate = _safe_int(payload["audioSampleRate"], audio.sample_rate)
        if "audioChannels" in payload:
            audio.channels = _safe_int(payload["audioChannels"], audio.channels)
        if "audioBitDepth" in payload:
            audio.bit_depth = _safe_int(payload["audioBitDepth"], audio.bit_depth)
        if "audioVolume" in payload:
            audio.volume = _safe_int(payload["audioVolume"], audio.volume)
        
        # Processing
        if "audioNoiseReduction" in payload:
            audio.noise_reduction = payload["audioNoiseReduction"] in (True, "true", "1", "on")
        if "audioNoiseThreshold" in payload:
            audio.noise_threshold = _safe_int(payload["audioNoiseThreshold"], audio.noise_threshold)
        
        # Encoding
        if "audioCodec" in payload:
            audio.codec = payload["audioCodec"]
        if "audioBitrate" in payload:
            audio.bitrate = _safe_int(payload["audioBitrate"], audio.bitrate)
        
        # Association
        if "audioLinkedCamera" in payload:
            audio.linked_camera_id = payload["audioLinkedCamera"]
        
        # Save to individual file
        self._save_audio_config(audio_id)
        return {"status": "ok", "audio": audio_id}

    def add_audio_device(self, name: str = "", device_id: str = "") -> Dict[str, Any]:
        """Add a new audio device with its own configuration file."""
        # Find next available ID
        existing_ids = [int(aid) for aid in self._audio_devices.keys() if aid.isdigit()]
        next_id = str(max(existing_ids, default=0) + 1)
        
        audio_name = name if name else f"Audio {next_id}"
        
        # Auto-detect stable audio ID on Linux
        stable_audio_id = find_stable_audio_id(device_id) if device_id else ""
        device_settings = {}
        if stable_audio_id:
            device_settings["stable_id"] = stable_audio_id
            logger.info("Auto-detected stable audio ID for %s: %s -> '%s'", 
                       next_id, device_id, stable_audio_id)
        
        new_audio = AudioConfig(
            identifier=next_id,
            name=audio_name,
            enabled=True,
            device_id=device_id,
            device_settings=device_settings,
        )
        self._audio_devices[next_id] = new_audio
        
        # Save to individual file
        self._save_audio_config(next_id)
        
        logger.info("Added audio device %s: %s (device=%s)", next_id, audio_name, device_id)
        return {
            "status": "ok",
            "audio": {
                "id": next_id,
                "name": audio_name,
                "enabled": True,
            }
        }

    def remove_audio_device(self, audio_id: str) -> Dict[str, str]:
        """Remove an audio device and delete its configuration file."""
        if audio_id not in self._audio_devices:
            raise KeyError(f"Audio device {audio_id} not found")
        
        del self._audio_devices[audio_id]
        self._delete_audio_config_file(audio_id)
        
        logger.info("Removed audio device %s", audio_id)
        return {"status": "ok", "removed": audio_id}

    # Meeting API configuration getters
    def get_meeting_config(self) -> Dict[str, Any]:
        """Get Meeting API configuration."""
        return {
            "server_url": self._meeting_server_url,
            "device_key": self._meeting_device_key,
            "token_code": self._meeting_token_code,
            "heartbeat_interval": self._meeting_heartbeat_interval,
        }

    @property
    def meeting_server_url(self) -> str:
        return self._meeting_server_url

    @property
    def meeting_device_key(self) -> str:
        return self._meeting_device_key

    @property
    def meeting_token_code(self) -> str:
        return self._meeting_token_code

    @property
    def meeting_heartbeat_interval(self) -> int:
        return self._meeting_heartbeat_interval

    @property
    def frontend_version(self) -> str:
        """Get frontend version dynamically from CHANGELOG.md."""
        return updater.get_current_version()