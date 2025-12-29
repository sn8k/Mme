# File Version: 0.2.2
"""
System information detection module for Motion Frontend.

Detects installed software versions (Motion, FFmpeg) and system utilities.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# Common paths where Motion might be installed
MOTION_PATHS = [
    "motion",  # System PATH
    "/usr/bin/motion",
    "/usr/local/bin/motion",
    "/opt/motion/bin/motion",
    "/snap/bin/motion",
]

# Common paths where FFmpeg might be installed
FFMPEG_PATHS = [
    "ffmpeg",  # System PATH
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/ffmpeg/bin/ffmpeg",
    "/snap/bin/ffmpeg",
]


@dataclass
class SystemVersions:
    """Container for detected system software versions."""
    motion_version: Optional[str] = None
    ffmpeg_version: Optional[str] = None
    python_version: Optional[str] = None


def _find_executable(candidates: List[str]) -> Optional[str]:
    """
    Find the first existing executable from a list of candidates.
    
    Args:
        candidates: List of executable paths to try.
        
    Returns:
        First found executable path, or None if none found.
    """
    for candidate in candidates:
        # Check if it's in PATH or an absolute path that exists
        if shutil.which(candidate):
            return candidate
        # For absolute paths, check directly
        if candidate.startswith("/") and Path(candidate).exists():
            return candidate
    return None


def _run_command(cmd: list[str], timeout: int = 5) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return result.stderr.strip() if result.stderr else None
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out: %s", " ".join(cmd))
        return None
    except Exception as e:
        logger.debug("Error running command %s: %s", cmd, e)
        return None


def detect_motion_version() -> Optional[str]:
    """
    Detect Motion version if installed.
    
    Tries multiple common paths and command line options.
    
    Returns:
        Version string (e.g., "4.6.0") or None if not found.
    """
    # Find motion executable
    motion_bin = _find_executable(MOTION_PATHS)
    if not motion_bin:
        logger.debug("Motion executable not found in any known path")
        return None
    
    logger.debug("Found Motion at: %s", motion_bin)
    
    # Try 'motion -h' first as 'motion --version' may not exist on all versions
    output = _run_command([motion_bin, "-h"])
    if output:
        # Motion help output typically starts with "motion Version X.Y.Z" or "Motion 4.x.x"
        # Try multiple patterns
        patterns = [
            r"[Mm]otion\s+[Vv]ersion\s+(\d+\.\d+(?:\.\d+)?)",  # "motion Version 4.6.0"
            r"[Mm]otion\s+(\d+\.\d+(?:\.\d+)?)",               # "Motion 4.6.0"
            r"version\s+(\d+\.\d+(?:\.\d+)?)",                  # "version 4.6.0"
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                version = match.group(1)
                logger.info("Detected Motion version: %s (from -h)", version)
                return version
    
    # Try 'motion -v' or 'motion --version'
    for flag in ["-v", "--version"]:
        output = _run_command([motion_bin, flag])
        if output:
            # Try to extract version number
            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
            if match:
                version = match.group(1)
                logger.info("Detected Motion version: %s (from %s)", version, flag)
                return version
    
    # Motion found but couldn't parse version - return "installed" indicator
    logger.info("Motion found at %s but version not parseable", motion_bin)
    return "installé"


def detect_ffmpeg_version() -> Optional[str]:
    """
    Detect FFmpeg version if installed.
    
    Tries multiple common paths.
    
    Returns:
        Version string (e.g., "6.1.1") or None if not found.
    """
    # Find ffmpeg executable
    ffmpeg_bin = _find_executable(FFMPEG_PATHS)
    if not ffmpeg_bin:
        logger.debug("FFmpeg executable not found in any known path")
        return None
    
    logger.debug("Found FFmpeg at: %s", ffmpeg_bin)
    
    output = _run_command([ffmpeg_bin, "-version"])
    if output:
        # FFmpeg version output: "ffmpeg version N.N.N ..."
        # Can also be "ffmpeg version n6.1-2-g..." for git builds
        match = re.search(r"ffmpeg version\s+[nN]?(\d+\.\d+(?:\.\d+)?)", output)
        if match:
            version = match.group(1)
            logger.info("Detected FFmpeg version: %s", version)
            return version
        
        # Try alternative format for git builds
        match = re.search(r"ffmpeg version\s+([^\s]+)", output)
        if match:
            version = match.group(1)
            logger.info("Detected FFmpeg version: %s", version)
            return version
    
    logger.debug("FFmpeg found but version not detectable")
    return None


def detect_all_versions() -> SystemVersions:
    """
    Detect all relevant software versions.
    
    Returns:
        SystemVersions dataclass with all detected versions.
    """
    return SystemVersions(
        motion_version=detect_motion_version(),
        ffmpeg_version=detect_ffmpeg_version(),
        python_version=platform.python_version(),
    )


# Cached versions (detected once at startup, can be refreshed)
_cached_versions: Optional[SystemVersions] = None


def get_system_versions(refresh: bool = False) -> SystemVersions:
    """
    Get system versions, using cached values unless refresh is requested.
    
    Args:
        refresh: If True, re-detect all versions.
        
    Returns:
        SystemVersions with cached or freshly detected versions.
    """
    global _cached_versions
    if _cached_versions is None or refresh:
        _cached_versions = detect_all_versions()
    return _cached_versions


def refresh_system_versions() -> SystemVersions:
    """Force refresh of cached system versions."""
    return get_system_versions(refresh=True)


def is_motion_running(port: int = 8081) -> bool:
    """
    Check if Motion daemon is running and listening on the specified port.
    
    On Linux, Motion is the preferred MJPEG source if available.
    This function checks if Motion is actively serving streams.
    
    Args:
        port: The port to check (default 8081, Motion's default stream port).
        
    Returns:
        True if Motion is running and the port is in use.
    """
    if platform.system().lower() != "linux":
        return False
    
    # Check if the port is listening
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            result = s.connect_ex(('127.0.0.1', port))
            if result == 0:
                # Port is open - check if it's Motion
                # Try to read from the process using /proc
                try:
                    output = subprocess.run(
                        ["ss", "-tlnp"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if output.returncode == 0 and f":{port}" in output.stdout:
                        if "motion" in output.stdout.lower():
                            logger.debug("Motion detected running on port %d", port)
                            return True
                except Exception:
                    pass
                
                # Alternative: check if motion process exists
                try:
                    result = subprocess.run(
                        ["pgrep", "-x", "motion"],
                        capture_output=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        logger.debug("Motion process detected (pgrep)")
                        return True
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Error checking Motion status: %s", e)
    
    return False


def get_motion_stream_url(port: int = 8081, camera_id: str = "1") -> Optional[str]:
    """
    Get the Motion stream URL for a camera if Motion is running.
    
    Args:
        port: Motion stream port.
        camera_id: Camera identifier (for multi-camera setups).
        
    Returns:
        Stream URL if Motion is available, None otherwise.
    """
    if is_motion_running(port):
        return f"http://127.0.0.1:{port}/"
    return None
