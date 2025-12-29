# -*- coding: utf-8 -*-
"""
Camera detection module for Motion Frontend.
Detects available cameras on Windows and Linux systems.

Version: 0.3.0
"""

import platform
import subprocess
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CameraControl:
    """Represents a camera control (brightness, contrast, etc.)."""
    id: str  # Internal ID (e.g., 'brightness', 'contrast')
    name: str  # Display name
    type: str  # 'int', 'bool', 'menu'
    value: int = 0  # Current value
    default: int = 0  # Default value
    min_val: int = 0  # Minimum value
    max_val: int = 100  # Maximum value
    step: int = 1  # Step increment
    menu_items: Optional[Dict[int, str]] = None  # For menu type controls
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "value": self.value,
            "default": self.default,
            "min": self.min_val,
            "max": self.max_val,
            "step": self.step,
        }
        if self.menu_items:
            result["menu_items"] = self.menu_items
        return result


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
    stable_path: str = ""  # Stable path via /dev/v4l/by-id/ or /dev/v4l/by-path/
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_path": self.device_path,
            "name": self.name,
            "driver": self.driver,
            "bus_info": self.bus_info,
            "capabilities": self.capabilities,
            "is_capture_device": self.is_capture_device,
            "source_type": self.source_type,
            "stable_path": self.stable_path,
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
    
    def _get_stable_path(self, device_path: str) -> str:
        """Get a stable device path that survives reboots.
        
        Linux assigns /dev/videoX numbers dynamically based on probe order,
        which can change between reboots. Stable paths via /dev/v4l/by-id/
        or /dev/v4l/by-path/ are based on USB port or device serial.
        
        Args:
            device_path: The dynamic device path (e.g., /dev/video0)
            
        Returns:
            Stable path if found, empty string otherwise.
        """
        if self._system != "linux":
            return ""
        
        try:
            import os
            import glob
            
            # Resolve the device to its real path
            real_device = os.path.realpath(device_path)
            
            # Look for stable symlinks in order of preference
            # by-id is most stable (based on device serial/model)
            # by-path is based on physical USB port location
            for search_dir in ["/dev/v4l/by-id", "/dev/v4l/by-path"]:
                if not os.path.isdir(search_dir):
                    continue
                
                for symlink in glob.glob(f"{search_dir}/*"):
                    try:
                        if os.path.realpath(symlink) == real_device:
                            logger.debug("Found stable path for %s: %s", device_path, symlink)
                            return symlink
                    except Exception:
                        continue
        
        except Exception as e:
            logger.debug("Error finding stable path for %s: %s", device_path, e)
        
        return ""
    
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
                    
                    # Get stable device path
                    stable_path = self._get_stable_path(device_path)
                    
                    camera = DetectedCamera(
                        device_path=device_path,
                        name=current_name or f"Camera {device_path}",
                        driver=current_driver,
                        capabilities=caps,
                        is_capture_device=is_capture,
                        source_type=source_type,
                        stable_path=stable_path,
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
                
                # Get stable device path
                stable_path = self._get_stable_path(device_path)
                
                camera = DetectedCamera(
                    device_path=device_path,
                    name=name,
                    source_type="v4l2",
                    stable_path=stable_path,
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

    # ========================================================================
    # Camera Controls Detection
    # ========================================================================
    
    def detect_camera_controls(self, device_path: str) -> List[CameraControl]:
        """Detect available controls for a camera device.
        
        Args:
            device_path: Device path (/dev/video0) or index (0, 1).
            
        Returns:
            List of available camera controls.
        """
        if self._system == "linux":
            return self._detect_v4l2_controls(device_path)
        elif self._system == "windows":
            return self._detect_windows_controls(device_path)
        else:
            logger.warning("Unsupported platform for camera controls: %s", self._system)
            return []
    
    def _detect_v4l2_controls(self, device_path: str) -> List[CameraControl]:
        """Detect V4L2 controls using v4l2-ctl --list-ctrls."""
        controls = []
        
        try:
            # Get all controls with their values
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-ctrls-menus"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug("v4l2-ctl failed for %s: %s", device_path, result.stderr)
                return controls
            
            output = result.stdout
            current_control: Optional[CameraControl] = None
            
            for line in output.split("\n"):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                # Control line format:
                # brightness 0x00980900 (int)    : min=-64 max=64 step=1 default=0 value=0
                # auto_exposure 0x009a0901 (menu)   : min=0 max=3 default=3 value=3
                # power_line_frequency 0x00980918 (menu)   : min=0 max=2 default=1 value=1
                
                ctrl_match = re.match(
                    r'^\s*(\w+)\s+0x[0-9a-f]+\s+\((\w+)\)\s*:\s*(.+)$',
                    line_stripped,
                    re.IGNORECASE
                )
                
                if ctrl_match:
                    ctrl_name = ctrl_match.group(1)
                    ctrl_type = ctrl_match.group(2).lower()
                    ctrl_params = ctrl_match.group(3)
                    
                    # Parse parameters
                    params = {}
                    for param in ctrl_params.split():
                        if '=' in param:
                            key, val = param.split('=', 1)
                            try:
                                params[key] = int(val)
                            except ValueError:
                                params[key] = val
                    
                    # Map control type
                    if ctrl_type == 'int':
                        control_type = 'int'
                    elif ctrl_type == 'bool':
                        control_type = 'bool'
                    elif ctrl_type == 'menu':
                        control_type = 'menu'
                    elif ctrl_type == 'button':
                        continue  # Skip button controls
                    else:
                        control_type = 'int'
                    
                    # Create control
                    current_control = CameraControl(
                        id=ctrl_name,
                        name=self._format_control_name(ctrl_name),
                        type=control_type,
                        value=params.get('value', 0),
                        default=params.get('default', 0),
                        min_val=params.get('min', 0),
                        max_val=params.get('max', 100),
                        step=params.get('step', 1),
                        menu_items={} if control_type == 'menu' else None,
                    )
                    controls.append(current_control)
                
                # Menu item line format:
                #                 0: Manual Mode
                #                 1: Auto Mode
                elif current_control and current_control.type == 'menu':
                    menu_match = re.match(r'^\s+(\d+):\s+(.+)$', line)
                    if menu_match:
                        menu_idx = int(menu_match.group(1))
                        menu_label = menu_match.group(2).strip()
                        if current_control.menu_items is not None:
                            current_control.menu_items[menu_idx] = menu_label
            
            logger.info("Detected %d V4L2 controls for %s", len(controls), device_path)
            
        except FileNotFoundError:
            logger.debug("v4l2-ctl not found")
        except subprocess.TimeoutExpired:
            logger.warning("v4l2-ctl timed out for %s", device_path)
        except Exception as e:
            logger.error("Error detecting V4L2 controls for %s: %s", device_path, e)
        
        return controls
    
    def _detect_windows_controls(self, device_path: str) -> List[CameraControl]:
        """Detect camera controls via OpenCV on Windows."""
        controls = []
        
        try:
            import cv2
            
            # Parse device index
            try:
                device_index = int(device_path)
            except ValueError:
                # Try to extract index from "video=Name" format
                device_index = 0
            
            cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                logger.warning("Cannot open camera %s for control detection", device_path)
                return controls
            
            # OpenCV camera properties that can be controlled
            opencv_controls = [
                (cv2.CAP_PROP_BRIGHTNESS, "brightness", "Brightness", -100, 100),
                (cv2.CAP_PROP_CONTRAST, "contrast", "Contrast", -100, 100),
                (cv2.CAP_PROP_SATURATION, "saturation", "Saturation", -100, 100),
                (cv2.CAP_PROP_HUE, "hue", "Hue", -180, 180),
                (cv2.CAP_PROP_GAIN, "gain", "Gain", 0, 100),
                (cv2.CAP_PROP_EXPOSURE, "exposure", "Exposure", -13, 0),
                (cv2.CAP_PROP_SHARPNESS, "sharpness", "Sharpness", 0, 100),
                (cv2.CAP_PROP_GAMMA, "gamma", "Gamma", 0, 500),
                (cv2.CAP_PROP_WB_TEMPERATURE, "white_balance_temperature", "White Balance", 2000, 10000),
                (cv2.CAP_PROP_BACKLIGHT, "backlight_compensation", "Backlight", 0, 4),
                (cv2.CAP_PROP_FOCUS, "focus", "Focus", 0, 255),
                (cv2.CAP_PROP_ZOOM, "zoom", "Zoom", 0, 500),
                (cv2.CAP_PROP_PAN, "pan", "Pan", -180, 180),
                (cv2.CAP_PROP_TILT, "tilt", "Tilt", -180, 180),
            ]
            
            # Auto controls (bool type)
            opencv_auto_controls = [
                (cv2.CAP_PROP_AUTO_EXPOSURE, "auto_exposure", "Auto Exposure"),
                (cv2.CAP_PROP_AUTOFOCUS, "autofocus", "Auto Focus"),
                (cv2.CAP_PROP_AUTO_WB, "auto_white_balance", "Auto White Balance"),
            ]
            
            # Test each control
            for prop_id, ctrl_id, ctrl_name, min_val, max_val in opencv_controls:
                try:
                    value = cap.get(prop_id)
                    if value != -1 and value != 0:  # -1 usually means not supported
                        # Try to set and get to verify it's writable
                        original = value
                        test_val = (min_val + max_val) / 2
                        cap.set(prop_id, test_val)
                        new_val = cap.get(prop_id)
                        cap.set(prop_id, original)  # Restore
                        
                        # If value changed, control is supported
                        if new_val != original or value != 0:
                            controls.append(CameraControl(
                                id=ctrl_id,
                                name=ctrl_name,
                                type='int',
                                value=int(original),
                                default=int((min_val + max_val) / 2),
                                min_val=min_val,
                                max_val=max_val,
                                step=1,
                            ))
                except Exception:
                    pass
            
            # Test auto controls
            for prop_id, ctrl_id, ctrl_name in opencv_auto_controls:
                try:
                    value = cap.get(prop_id)
                    if value != -1:
                        controls.append(CameraControl(
                            id=ctrl_id,
                            name=ctrl_name,
                            type='bool',
                            value=int(value) if value > 0 else 0,
                            default=1,
                            min_val=0,
                            max_val=1,
                            step=1,
                        ))
                except Exception:
                    pass
            
            cap.release()
            logger.info("Detected %d OpenCV controls for %s", len(controls), device_path)
            
        except ImportError:
            logger.debug("OpenCV not available for control detection")
        except Exception as e:
            logger.error("Error detecting Windows controls for %s: %s", device_path, e)
        
        return controls
    
    def set_camera_control(self, device_path: str, control_id: str, value: int) -> bool:
        """Set a camera control value.
        
        Args:
            device_path: Device path or index.
            control_id: Control identifier.
            value: Value to set.
            
        Returns:
            True if successful, False otherwise.
        """
        if self._system == "linux":
            return self._set_v4l2_control(device_path, control_id, value)
        elif self._system == "windows":
            return self._set_windows_control(device_path, control_id, value)
        return False
    
    def _set_v4l2_control(self, device_path: str, control_id: str, value: int) -> bool:
        """Set a V4L2 control value."""
        try:
            result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "-c", f"{control_id}={value}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("Set V4L2 control %s=%d on %s", control_id, value, device_path)
                return True
            else:
                logger.warning("Failed to set V4L2 control %s on %s: %s", 
                              control_id, device_path, result.stderr)
                return False
        except Exception as e:
            logger.error("Error setting V4L2 control %s on %s: %s", control_id, device_path, e)
            return False
    
    def _set_windows_control(self, device_path: str, control_id: str, value: int) -> bool:
        """Set a Windows/OpenCV camera control value."""
        try:
            import cv2
            
            # Map control ID to OpenCV property
            control_map = {
                'brightness': cv2.CAP_PROP_BRIGHTNESS,
                'contrast': cv2.CAP_PROP_CONTRAST,
                'saturation': cv2.CAP_PROP_SATURATION,
                'hue': cv2.CAP_PROP_HUE,
                'gain': cv2.CAP_PROP_GAIN,
                'exposure': cv2.CAP_PROP_EXPOSURE,
                'sharpness': cv2.CAP_PROP_SHARPNESS,
                'gamma': cv2.CAP_PROP_GAMMA,
                'white_balance_temperature': cv2.CAP_PROP_WB_TEMPERATURE,
                'backlight_compensation': cv2.CAP_PROP_BACKLIGHT,
                'focus': cv2.CAP_PROP_FOCUS,
                'zoom': cv2.CAP_PROP_ZOOM,
                'pan': cv2.CAP_PROP_PAN,
                'tilt': cv2.CAP_PROP_TILT,
                'auto_exposure': cv2.CAP_PROP_AUTO_EXPOSURE,
                'autofocus': cv2.CAP_PROP_AUTOFOCUS,
                'auto_white_balance': cv2.CAP_PROP_AUTO_WB,
            }
            
            if control_id not in control_map:
                logger.warning("Unknown control ID: %s", control_id)
                return False
            
            try:
                device_index = int(device_path)
            except ValueError:
                device_index = 0
            
            cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return False
            
            success = cap.set(control_map[control_id], value)
            cap.release()
            
            if success:
                logger.info("Set OpenCV control %s=%d on %s", control_id, value, device_path)
            return success
            
        except Exception as e:
            logger.error("Error setting Windows control %s on %s: %s", control_id, device_path, e)
            return False
    
    def _format_control_name(self, control_id: str) -> str:
        """Format a control ID into a human-readable name."""
        # Replace underscores with spaces and capitalize
        name = control_id.replace('_', ' ').title()
        
        # Common replacements for better readability
        replacements = {
            'Auto Exposure': 'Auto Exposure',
            'White Balance Temperature': 'White Balance',
            'White Balance Temperature Auto': 'Auto White Balance',
            'Backlight Compensation': 'Backlight',
            'Power Line Frequency': 'Anti-Flicker',
            'Exposure Time Absolute': 'Exposure Time',
            'Focus Absolute': 'Focus',
            'Zoom Absolute': 'Zoom',
            'Pan Absolute': 'Pan',
            'Tilt Absolute': 'Tilt',
        }
        
        return replacements.get(name, name)


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


def detect_camera_controls(device_path: str) -> List[Dict[str, Any]]:
    """Detect available controls for a camera.
    
    Args:
        device_path: Device path or index.
        
    Returns:
        List of control dictionaries.
    """
    detector = get_detector()
    controls = detector.detect_camera_controls(device_path)
    return [c.to_dict() for c in controls]


def set_camera_control(device_path: str, control_id: str, value: int) -> bool:
    """Set a camera control value.
    
    Args:
        device_path: Device path or index.
        control_id: Control identifier.
        value: Value to set.
        
    Returns:
        True if successful.
    """
    return get_detector().set_camera_control(device_path, control_id, value)


def get_filter_patterns() -> List[str]:
    """Get current filter patterns."""
    return get_detector().filter_patterns


def set_filter_patterns(patterns: List[str]) -> None:
    """Set filter patterns."""
    get_detector().filter_patterns = patterns


def get_stable_device_path(device_path: str) -> str:
    """Get a stable device path for a camera.
    
    On Linux, /dev/videoX paths can change between reboots based on
    probe order. This function returns a stable path via /dev/v4l/by-id/
    or /dev/v4l/by-path/ that remains consistent.
    
    Args:
        device_path: The device path (e.g., /dev/video0)
        
    Returns:
        Stable path if found, or the original path if not.
    """
    detector = get_detector()
    stable = detector._get_stable_path(device_path)
    return stable if stable else device_path


def resolve_device_path(path: str) -> str:
    """Resolve a device path (stable or dynamic) to the actual device.
    
    If given a stable path (e.g., /dev/v4l/by-id/...), resolves it to
    the actual device (e.g., /dev/video0). If given a dynamic path,
    returns it unchanged.
    
    Args:
        path: Device path (stable or dynamic)
        
    Returns:
        The resolved device path.
    """
    import os
    try:
        if path.startswith("/dev/v4l/"):
            # This is a stable path, resolve to actual device
            return os.path.realpath(path)
        return path
    except Exception:
        return path
