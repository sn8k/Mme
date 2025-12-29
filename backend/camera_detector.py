# -*- coding: utf-8 -*-
"""
Camera detection module for Motion Frontend.
Detects available cameras on Windows and Linux systems.

Version: 0.1.0
"""

import platform
import subprocess
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class DetectedCamera:
    """Represents a detected camera device."""
    device_path: str  # /dev/video0 or camera index on Windows
    name: str
    driver: str = ""
    bus_info: str = ""
    capabilities: List[str] = field(default_factory=list)
    is_capture_device: bool = True
    source_type: str = "v4l2"  # v4l2, dshow, csi, usb
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_path": self.device_path,
            "name": self.name,
            "driver": self.driver,
            "bus_info": self.bus_info,
            "capabilities": self.capabilities,
            "is_capture_device": self.is_capture_device,
            "source_type": self.source_type,
        }


class CameraDetector:
    """Cross-platform camera detection."""
    
    # Default patterns to filter out (can be configured)
    DEFAULT_FILTER_PATTERNS = [
        r"bcm2835-isp",      # Raspberry Pi ISP (not a real camera)
        r"unicam",           # Raspberry Pi CSI internal
        r"rp1-cfe",          # Raspberry Pi 5 CSI internal
    ]
    
    def __init__(self, filter_patterns: Optional[List[str]] = None):
        """Initialize the camera detector.
        
        Args:
            filter_patterns: List of regex patterns to filter out devices.
        """
        self._filter_patterns = filter_patterns or self.DEFAULT_FILTER_PATTERNS.copy()
        self._system = platform.system().lower()
    
    @property
    def filter_patterns(self) -> List[str]:
        """Get the current filter patterns."""
        return self._filter_patterns
    
    @filter_patterns.setter
    def filter_patterns(self, patterns: List[str]) -> None:
        """Set filter patterns."""
        self._filter_patterns = patterns
    
    def add_filter_pattern(self, pattern: str) -> None:
        """Add a filter pattern."""
        if pattern not in self._filter_patterns:
            self._filter_patterns.append(pattern)
    
    def remove_filter_pattern(self, pattern: str) -> None:
        """Remove a filter pattern."""
        if pattern in self._filter_patterns:
            self._filter_patterns.remove(pattern)
    
    def _should_filter(self, camera: DetectedCamera) -> bool:
        """Check if a camera should be filtered out."""
        for pattern in self._filter_patterns:
            if re.search(pattern, camera.name, re.IGNORECASE):
                return True
            if re.search(pattern, camera.driver, re.IGNORECASE):
                return True
            if re.search(pattern, camera.device_path, re.IGNORECASE):
                return True
        return False
    
    def detect_cameras(self, include_filtered: bool = False) -> List[DetectedCamera]:
        """Detect available cameras on the system.
        
        Args:
            include_filtered: If True, include cameras that match filter patterns.
            
        Returns:
            List of detected cameras.
        """
        if self._system == "linux":
            cameras = self._detect_linux_cameras()
        elif self._system == "windows":
            cameras = self._detect_windows_cameras()
        else:
            logger.warning("Unsupported platform: %s", self._system)
            cameras = []
        
        if not include_filtered:
            cameras = [c for c in cameras if not self._should_filter(c)]
        
        return cameras
    
    def _detect_linux_cameras(self) -> List[DetectedCamera]:
        """Detect cameras on Linux using v4l2."""
        cameras = []
        
        # Try v4l2-ctl first (most reliable)
        cameras = self._detect_v4l2_cameras()
        
        # If no cameras found, try scanning /dev/video* directly
        if not cameras:
            cameras = self._detect_dev_video_cameras()
        
        return cameras
    
    def _detect_v4l2_cameras(self) -> List[DetectedCamera]:
        """Detect cameras using v4l2-ctl."""
        cameras = []
        
        try:
            # List all video devices
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug("v4l2-ctl not available or failed: %s", result.stderr)
                return cameras
            
            output = result.stdout
            current_name = ""
            current_driver = ""
            
            for line in output.split("\n"):
                line = line.strip()
                if not line:
                    continue
                
                # Device name line (not indented, ends with :)
                if not line.startswith("/dev") and line.endswith(":"):
                    # Parse device name and driver
                    # Format: "Device Name (driver):" or "Device Name:"
                    match = re.match(r"(.+?)\s*\(([^)]+)\)\s*:$", line)
                    if match:
                        current_name = match.group(1).strip()
                        current_driver = match.group(2).strip()
                    else:
                        current_name = line.rstrip(":")
                        current_driver = ""
                
                # Device path line (starts with /dev)
                elif line.startswith("/dev/video"):
                    device_path = line
                    
                    # Get device capabilities
                    caps = self._get_v4l2_capabilities(device_path)
                    is_capture = "video_capture" in caps or "VIDEO_CAPTURE" in caps
                    
                    # Determine source type
                    source_type = "v4l2"
                    if "csi" in current_driver.lower() or "unicam" in current_driver.lower():
                        source_type = "csi"
                    elif "usb" in current_driver.lower() or "uvc" in current_driver.lower():
                        source_type = "usb"
                    
                    camera = DetectedCamera(
                        device_path=device_path,
                        name=current_name or f"Camera {device_path}",
                        driver=current_driver,
                        capabilities=caps,
                        is_capture_device=is_capture,
                        source_type=source_type,
                    )
                    
                    # Only add capture devices
                    if is_capture:
                        cameras.append(camera)
        
        except FileNotFoundError:
            logger.debug("v4l2-ctl not found")
        except subprocess.TimeoutExpired:
            logger.warning("v4l2-ctl timed out")
        except Exception as e:
            logger.error("Error detecting v4l2 cameras: %s", e)
        
        return cameras
    
    def _get_v4l2_capabilities(self, device_path: str) -> List[str]:
        """Get capabilities of a v4l2 device."""
        caps = []
        
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--all"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout
                # Look for capabilities section
                if "Video Capture" in output or "video_capture" in output.lower():
                    caps.append("video_capture")
                if "Video Output" in output or "video_output" in output.lower():
                    caps.append("video_output")
                if "Streaming" in output:
                    caps.append("streaming")
        
        except Exception as e:
            logger.debug("Could not get capabilities for %s: %s", device_path, e)
        
        return caps
    
    def _detect_dev_video_cameras(self) -> List[DetectedCamera]:
        """Fallback: detect cameras by scanning /dev/video*."""
        cameras = []
        
        try:
            import glob
            video_devices = sorted(glob.glob("/dev/video*"))
            
            for device_path in video_devices:
                # Try to get device info via sysfs
                device_num = device_path.replace("/dev/video", "")
                name = f"Video Device {device_num}"
                
                # Try to read name from sysfs
                try:
                    with open(f"/sys/class/video4linux/video{device_num}/name", "r") as f:
                        name = f.read().strip()
                except:
                    pass
                
                camera = DetectedCamera(
                    device_path=device_path,
                    name=name,
                    source_type="v4l2",
                )
                cameras.append(camera)
        
        except Exception as e:
            logger.error("Error scanning /dev/video*: %s", e)
        
        return cameras
    
    def _detect_windows_cameras(self) -> List[DetectedCamera]:
        """Detect cameras on Windows using DirectShow."""
        cameras = []
        
        # Method 1: Try using PowerShell to query WMI
        cameras = self._detect_windows_wmi_cameras()
        
        # Method 2: Try using ffmpeg to list devices
        if not cameras:
            cameras = self._detect_windows_ffmpeg_cameras()
        
        # Method 3: Fallback - try OpenCV indices
        if not cameras:
            cameras = self._detect_windows_opencv_cameras()
        
        return cameras
    
    def _detect_windows_wmi_cameras(self) -> List[DetectedCamera]:
        """Detect cameras using Windows WMI via PowerShell."""
        cameras = []
        
        try:
            # Query for video capture devices via PowerShell
            ps_script = """
            Get-CimInstance Win32_PnPEntity | Where-Object { 
                $_.PNPClass -eq 'Camera' -or 
                $_.PNPClass -eq 'Image' -or
                $_.Name -match 'webcam|camera|video|capture' 
            } | Select-Object Name, DeviceID, PNPClass | ConvertTo-Json -Compress
            """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                import json
                try:
                    devices = json.loads(result.stdout)
                    if isinstance(devices, dict):
                        devices = [devices]
                    
                    for i, device in enumerate(devices):
                        name = device.get("Name", f"Camera {i}")
                        device_id = device.get("DeviceID", "")
                        
                        camera = DetectedCamera(
                            device_path=str(i),  # Index for DirectShow/OpenCV
                            name=name,
                            driver=device.get("PNPClass", "dshow"),
                            bus_info=device_id,
                            source_type="dshow",
                        )
                        cameras.append(camera)
                
                except json.JSONDecodeError:
                    logger.debug("Could not parse WMI output")
        
        except FileNotFoundError:
            logger.debug("PowerShell not available")
        except subprocess.TimeoutExpired:
            logger.warning("PowerShell WMI query timed out")
        except Exception as e:
            logger.error("Error detecting Windows WMI cameras: %s", e)
        
        return cameras
    
    def _detect_windows_ffmpeg_cameras(self) -> List[DetectedCamera]:
        """Detect cameras using ffmpeg on Windows."""
        cameras = []
        
        try:
            result = subprocess.run(
                ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # ffmpeg outputs device list to stderr
            output = result.stderr
            
            # Parse DirectShow devices
            # Format: [dshow @ ...] "Device Name" (video)
            video_device_pattern = r'\[dshow[^\]]*\]\s+"([^"]+)"\s+\(video\)'
            
            for match in re.finditer(video_device_pattern, output):
                name = match.group(1)
                
                camera = DetectedCamera(
                    device_path=f"video={name}",
                    name=name,
                    source_type="dshow",
                )
                cameras.append(camera)
        
        except FileNotFoundError:
            logger.debug("ffmpeg not found")
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg device list timed out")
        except Exception as e:
            logger.error("Error detecting ffmpeg cameras: %s", e)
        
        return cameras
    
    def _detect_windows_opencv_cameras(self) -> List[DetectedCamera]:
        """Fallback: detect cameras by trying OpenCV indices."""
        cameras = []
        
        try:
            import cv2
            
            # Try indices 0-9
            for i in range(10):
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    # Try to get camera name via backend
                    name = f"Camera {i}"
                    
                    camera = DetectedCamera(
                        device_path=str(i),
                        name=name,
                        source_type="dshow",
                    )
                    cameras.append(camera)
                    cap.release()
                else:
                    # Stop if we hit a non-existent camera
                    cap.release()
                    if i > 0:  # Allow index 0 to fail, but stop after first gap
                        break
        
        except ImportError:
            logger.debug("OpenCV not available for camera detection")
        except Exception as e:
            logger.error("Error detecting OpenCV cameras: %s", e)
        
        return cameras


# Global detector instance
_detector: Optional[CameraDetector] = None


def get_detector() -> CameraDetector:
    """Get the global camera detector instance."""
    global _detector
    if _detector is None:
        _detector = CameraDetector()
    return _detector


def detect_cameras(include_filtered: bool = False) -> List[Dict[str, Any]]:
    """Detect available cameras.
    
    Args:
        include_filtered: If True, include cameras that match filter patterns.
        
    Returns:
        List of camera dictionaries.
    """
    detector = get_detector()
    cameras = detector.detect_cameras(include_filtered=include_filtered)
    return [c.to_dict() for c in cameras]


def get_filter_patterns() -> List[str]:
    """Get current filter patterns."""
    return get_detector().filter_patterns


def set_filter_patterns(patterns: List[str]) -> None:
    """Set filter patterns."""
    get_detector().filter_patterns = patterns
