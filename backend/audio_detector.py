# -*- coding: utf-8 -*-
"""
Audio input detection module for Motion Frontend.
Detects available audio input devices on Windows and Linux (ALSA) systems.

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
class DetectedAudioDevice:
    """Represents a detected audio input device."""
    device_id: str  # hw:0,0 on Linux (ALSA), index or name on Windows
    name: str
    driver: str = ""
    card_name: str = ""
    channels: int = 2
    sample_rates: List[int] = field(default_factory=lambda: [44100, 48000])
    is_input: bool = True
    source_type: str = "alsa"  # alsa, wasapi, dshow
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "driver": self.driver,
            "card_name": self.card_name,
            "channels": self.channels,
            "sample_rates": self.sample_rates,
            "is_input": self.is_input,
            "source_type": self.source_type,
        }


class AudioDetector:
    """Cross-platform audio input detection."""
    
    # Default patterns to filter out (can be configured)
    DEFAULT_FILTER_PATTERNS = [
        r"hdmi",           # HDMI audio outputs (not inputs)
        r"spdif",          # S/PDIF outputs
        r"loopback",       # Loopback devices
    ]
    
    def __init__(self, filter_patterns: Optional[List[str]] = None):
        """Initialize the audio detector.
        
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
    
    def _should_filter(self, device: DetectedAudioDevice) -> bool:
        """Check if a device should be filtered out."""
        for pattern in self._filter_patterns:
            if re.search(pattern, device.name, re.IGNORECASE):
                return True
            if re.search(pattern, device.driver, re.IGNORECASE):
                return True
            if re.search(pattern, device.device_id, re.IGNORECASE):
                return True
            if re.search(pattern, device.card_name, re.IGNORECASE):
                return True
        return False
    
    def detect_devices(self, include_filtered: bool = False) -> List[DetectedAudioDevice]:
        """Detect available audio input devices on the system.
        
        Args:
            include_filtered: If True, include devices that match filter patterns.
            
        Returns:
            List of detected audio devices.
        """
        if self._system == "linux":
            devices = self._detect_linux_devices()
        elif self._system == "windows":
            devices = self._detect_windows_devices()
        else:
            logger.warning("Unsupported platform for audio detection: %s", self._system)
            devices = []
        
        if not include_filtered:
            devices = [d for d in devices if not self._should_filter(d)]
        
        return devices
    
    def _detect_linux_devices(self) -> List[DetectedAudioDevice]:
        """Detect audio input devices on Linux using ALSA."""
        devices = []
        
        # Try arecord first (most reliable for capture devices)
        devices = self._detect_alsa_arecord()
        
        # If no devices found, try scanning /proc/asound directly
        if not devices:
            devices = self._detect_proc_asound()
        
        return devices
    
    def _detect_alsa_arecord(self) -> List[DetectedAudioDevice]:
        """Detect audio capture devices using arecord -L."""
        devices = []
        
        try:
            # List all capture devices with arecord
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.debug("arecord not available or failed: %s", result.stderr)
                return devices
            
            output = result.stdout
            
            # Parse output format:
            # card 0: PCH [HDA Intel PCH], device 0: ALC898 Analog [ALC898 Analog]
            #   Subdevices: 1/1
            #   Subdevice #0: subdevice #0
            card_pattern = r"card (\d+): (\w+) \[([^\]]+)\], device (\d+): ([^\[]+) \[([^\]]+)\]"
            
            for match in re.finditer(card_pattern, output):
                card_num = match.group(1)
                card_id = match.group(2)
                card_name = match.group(3)
                device_num = match.group(4)
                device_name = match.group(5).strip()
                device_full_name = match.group(6)
                
                device = DetectedAudioDevice(
                    device_id=f"hw:{card_num},{device_num}",
                    name=device_full_name or device_name,
                    driver="alsa",
                    card_name=card_name,
                    source_type="alsa",
                    is_input=True,
                )
                devices.append(device)
        
        except FileNotFoundError:
            logger.debug("arecord not found, trying alternate methods")
        except subprocess.TimeoutExpired:
            logger.warning("arecord timed out")
        except Exception as e:
            logger.error("Error detecting ALSA devices with arecord: %s", e)
        
        # Also try arecord -L for more device names
        try:
            result = subprocess.run(
                ["arecord", "-L"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout
                # Parse named devices (plughw, default, etc.)
                # Format is device name followed by description on next line
                lines = output.strip().split('\n')
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line and not line.startswith(' ') and ':' not in line:
                        # This is a device name
                        device_name = line
                        description = ""
                        # Check for description on next line
                        if i + 1 < len(lines) and lines[i + 1].startswith('    '):
                            description = lines[i + 1].strip()
                        
                        # Only add if it's a capture device name
                        if any(kw in device_name.lower() for kw in ['plughw', 'hw:', 'default', 'sysdefault']):
                            # Check if we already have this device
                            exists = any(d.device_id == device_name for d in devices)
                            if not exists:
                                device = DetectedAudioDevice(
                                    device_id=device_name,
                                    name=description or device_name,
                                    driver="alsa",
                                    source_type="alsa",
                                    is_input=True,
                                )
                                devices.append(device)
                    i += 1
        except Exception as e:
            logger.debug("Could not list ALSA devices with arecord -L: %s", e)
        
        return devices
    
    def _detect_proc_asound(self) -> List[DetectedAudioDevice]:
        """Fallback: detect audio devices by scanning /proc/asound."""
        devices = []
        
        try:
            import os
            
            asound_path = "/proc/asound"
            if not os.path.exists(asound_path):
                return devices
            
            # Read cards file
            cards_file = os.path.join(asound_path, "cards")
            if os.path.exists(cards_file):
                with open(cards_file, "r") as f:
                    content = f.read()
                
                # Parse cards
                # Format:
                #  0 [PCH            ]: HDA-Intel - HDA Intel PCH
                #                       HDA Intel PCH at 0xf7510000 irq 32
                card_pattern = r"\s*(\d+)\s+\[([^\]]+)\]:\s+([^\-]+)\s+-\s+(.+)"
                
                for match in re.finditer(card_pattern, content):
                    card_num = match.group(1).strip()
                    card_id = match.group(2).strip()
                    driver = match.group(3).strip()
                    card_name = match.group(4).strip()
                    
                    # Check if this card has capture devices
                    pcm_path = os.path.join(asound_path, f"card{card_num}", "pcm0c")
                    if os.path.exists(pcm_path):
                        device = DetectedAudioDevice(
                            device_id=f"hw:{card_num},0",
                            name=card_name,
                            driver=driver,
                            card_name=card_name,
                            source_type="alsa",
                            is_input=True,
                        )
                        devices.append(device)
        
        except Exception as e:
            logger.error("Error scanning /proc/asound: %s", e)
        
        return devices
    
    def _detect_windows_devices(self) -> List[DetectedAudioDevice]:
        """Detect audio input devices on Windows."""
        devices = []
        
        # Method 1: Try using PowerShell to query audio devices
        devices = self._detect_windows_powershell()
        
        # Method 2: Try using ffmpeg to list devices
        if not devices:
            devices = self._detect_windows_ffmpeg()
        
        return devices
    
    def _detect_windows_powershell(self) -> List[DetectedAudioDevice]:
        """Detect audio input devices using Windows PowerShell/WMI."""
        devices = []
        
        try:
            # Query for audio capture devices via PowerShell using Get-PnpDevice
            ps_script = """
            Get-PnpDevice -Class AudioEndpoint -Status OK | Where-Object {
                $_.FriendlyName -match 'Microphone|Line In|Audio Input|Recording|Capture'
            } | Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json -Compress
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
                    endpoints = json.loads(result.stdout)
                    if isinstance(endpoints, dict):
                        endpoints = [endpoints]
                    
                    for i, endpoint in enumerate(endpoints):
                        name = endpoint.get("FriendlyName", f"Audio Input {i}")
                        instance_id = endpoint.get("InstanceId", "")
                        
                        device = DetectedAudioDevice(
                            device_id=str(i),
                            name=name,
                            driver="wasapi",
                            card_name=instance_id,
                            source_type="wasapi",
                            is_input=True,
                        )
                        devices.append(device)
                
                except json.JSONDecodeError:
                    logger.debug("Could not parse PowerShell audio endpoint output")
            
            # If no endpoints found, try WMI for audio devices
            if not devices:
                ps_script_wmi = """
                Get-CimInstance Win32_SoundDevice | Where-Object {
                    $_.Status -eq 'OK'
                } | Select-Object Name, DeviceID, Manufacturer, Status | ConvertTo-Json -Compress
                """
                
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script_wmi],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    import json
                    try:
                        sound_devices = json.loads(result.stdout)
                        if isinstance(sound_devices, dict):
                            sound_devices = [sound_devices]
                        
                        for i, snd_dev in enumerate(sound_devices):
                            name = snd_dev.get("Name", f"Sound Device {i}")
                            device_id = snd_dev.get("DeviceID", "")
                            manufacturer = snd_dev.get("Manufacturer", "")
                            
                            device = DetectedAudioDevice(
                                device_id=str(i),
                                name=name,
                                driver=manufacturer or "dshow",
                                card_name=device_id,
                                source_type="dshow",
                                is_input=True,  # Note: WMI doesn't distinguish input/output
                            )
                            devices.append(device)
                    
                    except json.JSONDecodeError:
                        logger.debug("Could not parse WMI sound device output")
        
        except FileNotFoundError:
            logger.debug("PowerShell not available")
        except subprocess.TimeoutExpired:
            logger.warning("PowerShell audio query timed out")
        except Exception as e:
            logger.error("Error detecting Windows audio devices: %s", e)
        
        return devices
    
    def _detect_windows_ffmpeg(self) -> List[DetectedAudioDevice]:
        """Detect audio devices using ffmpeg on Windows."""
        devices = []
        
        try:
            result = subprocess.run(
                ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # ffmpeg outputs device list to stderr
            output = result.stderr
            
            # Parse DirectShow audio devices
            # Format: [dshow @ ...] "Device Name" (audio)
            audio_device_pattern = r'\[dshow[^\]]*\]\s+"([^"]+)"\s+\(audio\)'
            
            for i, match in enumerate(re.finditer(audio_device_pattern, output)):
                name = match.group(1)
                
                device = DetectedAudioDevice(
                    device_id=f"audio={name}",
                    name=name,
                    driver="dshow",
                    source_type="dshow",
                    is_input=True,
                )
                devices.append(device)
        
        except FileNotFoundError:
            logger.debug("ffmpeg not found")
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg device list timed out")
        except Exception as e:
            logger.error("Error detecting ffmpeg audio devices: %s", e)
        
        return devices
    
    def get_device_capabilities(self, device_id: str) -> Dict[str, Any]:
        """Get detailed capabilities of an audio device.
        
        Args:
            device_id: The device identifier.
            
        Returns:
            Dictionary with device capabilities.
        """
        capabilities = {
            "device_id": device_id,
            "sample_rates": [8000, 16000, 22050, 44100, 48000],
            "channels": [1, 2],
            "bit_depths": [16, 24, 32],
        }
        
        if self._system == "linux":
            try:
                # Try to get actual capabilities from ALSA
                result = subprocess.run(
                    ["arecord", "-D", device_id, "--dump-hw-params"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    input=""  # Provide empty input to avoid hang
                )
                
                output = result.stderr + result.stdout
                
                # Parse sample rates
                rate_match = re.search(r"RATE:\s*\[(\d+)\s+(\d+)\]", output)
                if rate_match:
                    min_rate = int(rate_match.group(1))
                    max_rate = int(rate_match.group(2))
                    capabilities["min_sample_rate"] = min_rate
                    capabilities["max_sample_rate"] = max_rate
                
                # Parse channels
                chan_match = re.search(r"CHANNELS:\s*\[(\d+)\s+(\d+)\]", output)
                if chan_match:
                    min_chan = int(chan_match.group(1))
                    max_chan = int(chan_match.group(2))
                    capabilities["min_channels"] = min_chan
                    capabilities["max_channels"] = max_chan
            
            except Exception as e:
                logger.debug("Could not get ALSA device capabilities: %s", e)
        
        return capabilities


# Global detector instance
_detector: Optional[AudioDetector] = None


def get_detector() -> AudioDetector:
    """Get the global audio detector instance."""
    global _detector
    if _detector is None:
        _detector = AudioDetector()
    return _detector


def detect_audio_devices(include_filtered: bool = False) -> List[Dict[str, Any]]:
    """Detect available audio input devices.
    
    Args:
        include_filtered: If True, include devices that match filter patterns.
        
    Returns:
        List of audio device dictionaries.
    """
    detector = get_detector()
    devices = detector.detect_devices(include_filtered=include_filtered)
    return [d.to_dict() for d in devices]


def get_filter_patterns() -> List[str]:
    """Get current filter patterns."""
    return get_detector().filter_patterns


def set_filter_patterns(patterns: List[str]) -> None:
    """Set filter patterns."""
    get_detector().filter_patterns = patterns
