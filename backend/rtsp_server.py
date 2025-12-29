# File Version: 0.5.1
"""
RTSP Server module for Motion Frontend.

Provides RTSP streaming with video from camera and audio from linked audio device.
Uses FFmpeg for capture, encoding (H.264 + AAC) and RTSP streaming.

Cross-platform support:
- Windows: DirectShow for video, DirectShow/WASAPI for audio
- Linux: V4L2 for video, ALSA for audio

Requires:
- FFmpeg for encoding and streaming
- MediaMTX (or rtsp-simple-server) on Linux as RTSP server
- On Windows: FFmpeg can push to localhost RTSP URL if a server is running
"""

import asyncio
import logging
import platform
import shutil
import subprocess
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RTSPStreamConfig:
    """Configuration for an RTSP stream."""
    camera_id: str
    camera_device: str
    camera_name: str
    resolution: str = "1280x720"
    framerate: int = 25
    video_bitrate: int = 2000  # kbps
    
    # Audio settings (optional)
    audio_device_id: Optional[str] = None
    audio_device_name: Optional[str] = None
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    audio_bitrate: int = 128  # kbps
    audio_codec: str = "aac"
    
    # RTSP settings
    rtsp_port: int = 8554
    rtsp_path: str = "/stream"
    
    # Encoding settings
    video_codec: str = "libx264"
    preset: str = "ultrafast"  # For low latency
    tune: str = "zerolatency"


@dataclass
class RTSPStreamStatus:
    """Status of an RTSP stream."""
    camera_id: str
    is_running: bool = False
    rtsp_url: str = ""
    error: Optional[str] = None
    pid: Optional[int] = None
    has_audio: bool = False
    started_at: Optional[str] = None


class RTSPServer:
    """
    RTSP Server manager using FFmpeg.
    
    Each camera can have its own RTSP stream on a dedicated port.
    Audio from linked audio device is mixed into the stream if available.
    """
    
    def __init__(self):
        self._streams: Dict[str, subprocess.Popen] = {}
        self._stream_status: Dict[str, RTSPStreamStatus] = {}
        self._platform = platform.system().lower()
        self._ffmpeg_path: Optional[str] = None
        self._base_rtsp_port = 8554
        
    def _find_ffmpeg(self) -> Optional[str]:
        """Find FFmpeg executable."""
        if self._ffmpeg_path:
            return self._ffmpeg_path
            
        # Refresh PATH from environment (for winget installations)
        import os
        try:
            system_path = os.environ.get("PATH", "")
            # Add common Windows paths for winget and chocolatey installs
            additional_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"),
                r"C:\tools\ffmpeg\bin",
                r"C:\ffmpeg\bin",
            ]
            for p in additional_paths:
                if p not in system_path and os.path.isdir(p):
                    system_path = p + os.pathsep + system_path
            os.environ["PATH"] = system_path
        except Exception:
            pass
            
        # Try to find ffmpeg in PATH
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            self._ffmpeg_path = ffmpeg
            logger.info("Found FFmpeg at: %s", ffmpeg)
            return ffmpeg
            
        # Try common locations
        common_paths = []
        if self._platform == "windows":
            common_paths = [
                Path("C:/ffmpeg/bin/ffmpeg.exe"),
                Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
                Path("C:/Program Files/FFmpeg/bin/ffmpeg.exe"),
                Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
                # Winget install location
                Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe")),
            ]
            # Search in some common dev directories
            dev_paths = [
                Path("C:/Dev_VSCode"),
                Path("C:/Projects"),
                Path("C:/tools"),
            ]
            for dev_path in dev_paths:
                if dev_path.exists():
                    for ffmpeg_dir in dev_path.rglob("ffmpeg*.exe"):
                        if ffmpeg_dir.name.lower() == "ffmpeg.exe":
                            common_paths.append(ffmpeg_dir)
                            break
        else:
            common_paths = [
                Path("/usr/bin/ffmpeg"),
                Path("/usr/local/bin/ffmpeg"),
            ]
            
        for path in common_paths:
            if path.exists():
                self._ffmpeg_path = str(path)
                logger.info("Found FFmpeg at: %s", path)
                return self._ffmpeg_path
                
        logger.warning("FFmpeg not found in PATH or common locations")
        return None
        
    def is_ffmpeg_available(self) -> bool:
        """Check if FFmpeg is available."""
        return self._find_ffmpeg() is not None
    
    def _normalize_device_name(self, name: str) -> str:
        """Normalize device name for comparison (remove special chars, lowercase)."""
        # Normalize Unicode (NFKD removes special chars like ®)
        normalized = unicodedata.normalize('NFKD', name)
        # Remove non-ASCII characters
        ascii_name = normalized.encode('ASCII', 'ignore').decode('ASCII')
        # Lowercase and strip
        return ascii_name.lower().strip()
    
    def _list_dshow_devices(self, device_type: str = "video") -> List[str]:
        """
        List available DirectShow devices using FFmpeg.
        
        Args:
            device_type: "video" or "audio"
            
        Returns:
            List of device names as reported by FFmpeg.
        """
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return []
            
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace'
            )
            # FFmpeg outputs device list to stderr
            output = result.stderr
            
            devices = []
            
            # FFmpeg format: [dshow @ ...] "Device Name" (type)
            # where type is "video", "audio", or "none"
            # Followed by: [dshow @ ...]   Alternative name "@device_pnp_..."
            for line in output.split('\n'):
                # Match lines like: [dshow @ ...] "Microsoft® LifeCam HD-5000" (video)
                match = re.search(r'\[dshow @ [^\]]+\]\s*"([^"]+)"\s*\((\w+)\)', line)
                if match:
                    device_name = match.group(1)
                    detected_type = match.group(2)
                    # Match by type (video, audio) or accept 'none' which can be either
                    if detected_type == device_type or detected_type == "none":
                        devices.append(device_name)
                        logger.debug("Found DirectShow %s device: %s", device_type, device_name)
                            
            logger.debug("Found %d DirectShow %s devices: %s", len(devices), device_type, devices)
            return devices
        except Exception as e:
            logger.error("Failed to list DirectShow devices: %s", e)
            return []
    
    def _find_matching_dshow_device(self, name: str, device_type: str = "video") -> Optional[str]:
        """
        Find the exact DirectShow device name that matches the given name.
        
        Uses fuzzy matching to handle special characters (e.g., ® symbol).
        
        Args:
            name: Camera/device name (may be missing special chars)
            device_type: "video" or "audio"
            
        Returns:
            Exact DirectShow device name, or None if not found.
        """
        devices = self._list_dshow_devices(device_type)
        if not devices:
            return None
            
        # First try exact match
        if name in devices:
            return name
            
        # Try normalized matching
        normalized_search = self._normalize_device_name(name)
        for device in devices:
            normalized_device = self._normalize_device_name(device)
            if normalized_search == normalized_device:
                logger.info("Matched device '%s' to DirectShow device '%s'", name, device)
                return device
            # Also try if one contains the other
            if normalized_search in normalized_device or normalized_device in normalized_search:
                logger.info("Partial match: '%s' to DirectShow device '%s'", name, device)
                return device
                
        logger.warning("Could not find matching DirectShow device for '%s'. Available: %s", name, devices)
        return None
        
    def get_ffmpeg_version(self) -> Optional[str]:
        """Get FFmpeg version string."""
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return None
            
        try:
            result = subprocess.run(
                [ffmpeg, "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Extract version from first line
            first_line = result.stdout.split('\n')[0]
            match = re.search(r'ffmpeg version (\S+)', first_line)
            if match:
                return match.group(1)
            return first_line
        except Exception as e:
            logger.error("Failed to get FFmpeg version: %s", e)
            return None
    
    def _get_video_input_args(self, config: RTSPStreamConfig) -> List[str]:
        """Get FFmpeg input arguments for video capture."""
        args = []
        
        if self._platform == "windows":
            # DirectShow input on Windows
            # If device is just a number (OpenCV index), try to use the camera name
            device = config.camera_device
            if device.isdigit():
                # Use camera name as DirectShow device name instead of index
                # FFmpeg DirectShow needs the actual device name, not OpenCV index
                device = config.camera_name
                
            # Try to find exact DirectShow device name (may have special chars like ®)
            exact_device = self._find_matching_dshow_device(device, "video")
            if exact_device:
                device = exact_device
            else:
                logger.warning("Could not find exact DirectShow match for '%s', trying as-is", device)
            
            # Build arguments - on Windows, let FFmpeg auto-detect resolution if not standard
            # Common webcam resolutions that should work
            common_resolutions = [
                "640x480", "640x360", "320x240", "176x144", "160x120",
                "1280x720", "800x600", "960x544", "800x448", "424x240", "352x288"
            ]
            args.extend(["-f", "dshow"])
            # Only specify resolution if it's a common webcam resolution
            if config.resolution in common_resolutions:
                args.extend(["-video_size", config.resolution])
            else:
                # Try 1280x720 as a safe fallback for HD webcams
                logger.info("Resolution %s may not be supported, using auto-detect or 1280x720 fallback", config.resolution)
                args.extend(["-video_size", "1280x720"])
            args.extend([
                "-framerate", str(min(config.framerate, 30)),  # Cap at 30fps
                "-i", f"video={device}"
            ])
        else:
            # V4L2 input on Linux
            device = config.camera_device
            if not device.startswith("/dev/"):
                device = f"/dev/video{device}"
            args.extend([
                "-f", "v4l2",
                "-video_size", config.resolution,
                "-framerate", str(config.framerate),
                "-i", device
            ])
            
        return args
        
    def _get_audio_input_args(self, config: RTSPStreamConfig) -> List[str]:
        """Get FFmpeg input arguments for audio capture."""
        if not config.audio_device_id:
            return []
            
        args = []
        
        if self._platform == "windows":
            # DirectShow audio input on Windows
            args.extend([
                "-f", "dshow",
                "-sample_rate", str(config.audio_sample_rate),
                "-channels", str(config.audio_channels),
                "-i", f"audio={config.audio_device_id}"
            ])
        else:
            # ALSA input on Linux
            audio_device = config.audio_device_id
            # Ensure proper ALSA device format
            if not audio_device.startswith(("hw:", "plughw:", "default")):
                audio_device = f"hw:{audio_device}"
            args.extend([
                "-f", "alsa",
                "-sample_rate", str(config.audio_sample_rate),
                "-channels", str(config.audio_channels),
                "-i", audio_device
            ])
            
        return args
        
    def _get_encoding_args(self, config: RTSPStreamConfig, has_audio: bool) -> List[str]:
        """Get FFmpeg encoding arguments."""
        args = []
        
        # Video encoding
        args.extend([
            "-c:v", config.video_codec,
            "-preset", config.preset,
            "-tune", config.tune,
            "-b:v", f"{config.video_bitrate}k",
            "-maxrate", f"{config.video_bitrate * 2}k",
            "-bufsize", f"{config.video_bitrate}k",
            "-pix_fmt", "yuv420p",
            "-g", str(config.framerate * 2),  # GOP size = 2 seconds
        ])
        
        # Audio encoding (if audio present)
        if has_audio:
            if config.audio_codec == "aac":
                args.extend([
                    "-c:a", "aac",
                    "-b:a", f"{config.audio_bitrate}k",
                    "-ar", str(config.audio_sample_rate),
                    "-ac", str(config.audio_channels),
                ])
            elif config.audio_codec == "opus":
                args.extend([
                    "-c:a", "libopus",
                    "-b:a", f"{config.audio_bitrate}k",
                    "-ar", str(config.audio_sample_rate),
                    "-ac", str(config.audio_channels),
                ])
            elif config.audio_codec == "mp3":
                args.extend([
                    "-c:a", "libmp3lame",
                    "-b:a", f"{config.audio_bitrate}k",
                    "-ar", str(config.audio_sample_rate),
                    "-ac", str(config.audio_channels),
                ])
            else:  # pcm
                args.extend([
                    "-c:a", "pcm_s16le",
                    "-ar", str(config.audio_sample_rate),
                    "-ac", str(config.audio_channels),
                ])
        else:
            # No audio - disable audio stream
            args.extend(["-an"])
            
        return args
    
    def _find_mediamtx(self) -> Optional[str]:
        """Find MediaMTX executable (rtsp-simple-server / mediamtx)."""
        # Try common names
        for name in ["mediamtx", "rtsp-simple-server"]:
            path = shutil.which(name)
            if path:
                logger.info("Found MediaMTX at: %s", path)
                return path
        
        # On Linux, check common install locations
        if self._platform != "windows":
            linux_paths = [
                Path("/usr/local/bin/mediamtx"),
                Path("/opt/mediamtx/mediamtx"),
            ]
            for lp in linux_paths:
                if lp.exists():
                    logger.info("Found MediaMTX at: %s", lp)
                    return str(lp)
        
        logger.debug("MediaMTX not found in PATH or common locations")
        return None
    
    def _is_rtsp_port_listening(self, port: int) -> bool:
        """Check if something is listening on the RTSP port."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            listening = result == 0
            logger.debug("Port %d listening check: %s", port, listening)
            return listening
        except Exception as e:
            logger.debug("Port %d check failed: %s", port, e)
            return False
        finally:
            sock.close()
    
    def is_rtsp_server_available(self) -> bool:
        """Check if a proper RTSP server is available (MediaMTX/rtsp-simple-server).
        
        Note: FFmpeg alone cannot create an RTSP server - it can only push to one.
        MediaMTX or rtsp-simple-server is required to receive the stream.
        
        On both platforms, checks if something is listening on the default RTSP port.
        On Linux, also checks if MediaMTX binary exists (for installation status).
        """
        # First check if port is listening (works on both platforms)
        if self._is_rtsp_port_listening(self._base_rtsp_port):
            logger.info("RTSP server detected on port %d", self._base_rtsp_port)
            return True
        
        # On Linux, check if MediaMTX binary exists (may need to start service)
        if self._platform != "windows":
            mediamtx_path = self._find_mediamtx()
            if mediamtx_path:
                logger.info("MediaMTX binary found at %s but service not listening", mediamtx_path)
                return True  # Binary exists, we'll try to start it in start_stream()
            
        logger.warning("No RTSP server available on port %d", self._base_rtsp_port)
        return False
        
    def _get_rtsp_output_args(self, config: RTSPStreamConfig) -> List[str]:
        """Get FFmpeg RTSP output arguments."""
        rtsp_url = f"rtsp://127.0.0.1:{config.rtsp_port}{config.rtsp_path}"
        
        return [
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            rtsp_url
        ]
        
    def _build_ffmpeg_command(self, config: RTSPStreamConfig) -> Tuple[List[str], bool]:
        """
        Build complete FFmpeg command for RTSP streaming.
        
        Returns tuple of (command_args, has_audio).
        """
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found")
            
        has_audio = config.audio_device_id is not None
        
        cmd = [ffmpeg]
        
        # Global options
        cmd.extend([
            "-hide_banner",
            "-loglevel", "warning",
            "-y",  # Overwrite output
        ])
        
        # Video input
        cmd.extend(self._get_video_input_args(config))
        
        # Audio input (if available)
        if has_audio:
            cmd.extend(self._get_audio_input_args(config))
            
        # Encoding
        cmd.extend(self._get_encoding_args(config, has_audio))
        
        # RTSP output
        cmd.extend(self._get_rtsp_output_args(config))
        
        return cmd, has_audio
        
    async def start_stream(self, config: RTSPStreamConfig) -> RTSPStreamStatus:
        """Start RTSP stream for a camera.
        
        Note: RTSP streaming requires MediaMTX/rtsp-simple-server to receive the stream.
        FFmpeg alone can only push to an existing RTSP server, not create one.
        """
        camera_id = config.camera_id
        
        # Stop existing stream if running
        if camera_id in self._streams:
            await self.stop_stream(camera_id)
            
        status = RTSPStreamStatus(
            camera_id=camera_id,
            has_audio=config.audio_device_id is not None
        )
        
        # Check if RTSP server (MediaMTX) is available
        logger.info("Checking RTSP server availability for camera %s on port %d...", camera_id, config.rtsp_port)
        if not self.is_rtsp_server_available():
            status.is_running = False
            if self._platform == "windows":
                status.error = (
                    f"No RTSP server listening on port {self._base_rtsp_port}. "
                    "Please start MediaMTX or another RTSP server first. "
                    "Download MediaMTX from: https://github.com/bluenviron/mediamtx/releases"
                )
                logger.error("No RTSP server listening on port %d (Windows)", self._base_rtsp_port)
            else:
                status.error = (
                    "MediaMTX not found. "
                    "Run 'sudo bash scripts/install_motion_frontend.sh --repair' to install it, "
                    "or use the MJPEG stream instead."
                )
                logger.error("RTSP server (MediaMTX) not found - run --repair to install")
            self._stream_status[camera_id] = status
            return status
        
        # On Linux, ensure MediaMTX service is running
        if self._platform != "windows":
            if not self._is_rtsp_port_listening(config.rtsp_port):
                logger.info("MediaMTX not listening on port %d, attempting to start service...", config.rtsp_port)
                try:
                    # Check if service exists
                    result = subprocess.run(
                        ["systemctl", "is-active", "mediamtx"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    logger.debug("MediaMTX service status: %s (code %d)", result.stdout.strip(), result.returncode)
                    
                    if result.returncode != 0:
                        # Try to start it with sudo
                        logger.warning("MediaMTX service not running, attempting to start with sudo...")
                        start_result = subprocess.run(
                            ["sudo", "systemctl", "start", "mediamtx"],
                            capture_output=True,
                            text=True,
                            timeout=15
                        )
                        if start_result.returncode != 0:
                            logger.error("Failed to start MediaMTX service: %s", start_result.stderr)
                            status.is_running = False
                            status.error = f"Failed to start MediaMTX service: {start_result.stderr}"
                            self._stream_status[camera_id] = status
                            return status
                        else:
                            logger.info("MediaMTX service started successfully")
                            # Wait for the service to be ready
                            import time
                            for i in range(5):
                                time.sleep(1)
                                if self._is_rtsp_port_listening(config.rtsp_port):
                                    logger.info("MediaMTX now listening on port %d", config.rtsp_port)
                                    break
                            else:
                                logger.warning("MediaMTX service started but port %d not yet listening", config.rtsp_port)
                    else:
                        logger.info("MediaMTX service is active")
                except Exception as e:
                    logger.error("Could not check/start MediaMTX service: %s", e)
        
        try:
            cmd, has_audio = self._build_ffmpeg_command(config)
            status.has_audio = has_audio
            
            logger.info("="*60)
            logger.info("Starting RTSP stream for camera %s", camera_id)
            logger.info("FFmpeg command: %s", " ".join(cmd))
            logger.info("Target RTSP URL: rtsp://127.0.0.1:%d%s", config.rtsp_port, config.rtsp_path)
            logger.info("="*60)
            
            # Start FFmpeg process
            if self._platform == "windows":
                # Windows: CREATE_NO_WINDOW flag
                CREATE_NO_WINDOW = 0x08000000
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW
                )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
            self._streams[camera_id] = process
            
            # Wait a bit to check if process started successfully
            await asyncio.sleep(1.0)
            
            if process.poll() is not None:
                # Process terminated
                _, stderr = process.communicate(timeout=2)
                error_msg = stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
                status.is_running = False
                status.error = error_msg
                logger.error("RTSP stream failed to start: %s", error_msg)
            else:
                status.is_running = True
                status.pid = process.pid
                status.rtsp_url = f"rtsp://{{host}}:{config.rtsp_port}{config.rtsp_path}"
                status.started_at = __import__("datetime").datetime.now().isoformat()
                logger.info("RTSP stream started on port %d for camera %s", config.rtsp_port, camera_id)
                
        except Exception as e:
            status.is_running = False
            status.error = str(e)
            logger.error("Failed to start RTSP stream: %s", e)
            
        self._stream_status[camera_id] = status
        return status
        
    async def stop_stream(self, camera_id: str) -> bool:
        """Stop RTSP stream for a camera."""
        if camera_id not in self._streams:
            logger.warning("No RTSP stream running for camera %s", camera_id)
            return False
            
        process = self._streams[camera_id]
        
        try:
            # Terminate gracefully
            process.terminate()
            
            # Wait for process to end
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if not responding
                process.kill()
                process.wait(timeout=2)
                
            logger.info("RTSP stream stopped for camera %s", camera_id)
            
        except Exception as e:
            logger.error("Error stopping RTSP stream: %s", e)
            return False
        finally:
            del self._streams[camera_id]
            if camera_id in self._stream_status:
                self._stream_status[camera_id].is_running = False
                
        return True
        
    async def stop_all_streams(self) -> None:
        """Stop all RTSP streams."""
        camera_ids = list(self._streams.keys())
        for camera_id in camera_ids:
            await self.stop_stream(camera_id)
            
    def get_stream_status(self, camera_id: str) -> Optional[RTSPStreamStatus]:
        """Get status of RTSP stream for a camera."""
        status = self._stream_status.get(camera_id)
        
        if status and camera_id in self._streams:
            # Check if process is still running
            process = self._streams[camera_id]
            if process.poll() is not None:
                status.is_running = False
                # Try to get error from stderr
                try:
                    _, stderr = process.communicate(timeout=1)
                    if stderr:
                        status.error = stderr.decode("utf-8", errors="replace")
                except:
                    pass
                del self._streams[camera_id]
                
        return status
        
    def get_all_stream_status(self) -> Dict[str, RTSPStreamStatus]:
        """Get status of all RTSP streams."""
        # Update status for all streams
        for camera_id in list(self._streams.keys()):
            self.get_stream_status(camera_id)
        return self._stream_status.copy()
        
    def get_rtsp_port_for_camera(self, camera_id: str) -> int:
        """Calculate RTSP port for a camera based on its ID."""
        try:
            cam_num = int(camera_id)
            return self._base_rtsp_port + cam_num - 1
        except ValueError:
            # Hash-based port for non-numeric IDs
            return self._base_rtsp_port + (hash(camera_id) % 100)


# Singleton instance
_rtsp_server: Optional[RTSPServer] = None


def get_rtsp_server() -> RTSPServer:
    """Get the singleton RTSP server instance."""
    global _rtsp_server
    if _rtsp_server is None:
        _rtsp_server = RTSPServer()
    return _rtsp_server
