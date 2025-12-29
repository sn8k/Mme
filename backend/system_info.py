# File Version: 0.1.0
"""
System information detection module for Motion Frontend.

Detects installed software versions (Motion, FFmpeg) and system utilities.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SystemVersions:
    """Container for detected system software versions."""
    motion_version: Optional[str] = None
    ffmpeg_version: Optional[str] = None
    python_version: Optional[str] = None


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
    
    Returns:
        Version string (e.g., "4.6.0") or None if not found.
    """
    # Try 'motion -h' first as 'motion --version' may not exist
    output = _run_command(["motion", "-h"])
    if output:
        # Motion help output typically starts with "motion Version X.Y.Z"
        match = re.search(r"[Mm]otion\s+[Vv]ersion\s+(\d+\.\d+(?:\.\d+)?)", output)
        if match:
            version = match.group(1)
            logger.info("Detected Motion version: %s", version)
            return version
    
    # Try 'motion -v' or 'motion --version'
    for flag in ["-v", "--version"]:
        output = _run_command(["motion", flag])
        if output:
            # Try to extract version number
            match = re.search(r"(\d+\.\d+(?:\.\d+)?)", output)
            if match:
                version = match.group(1)
                logger.info("Detected Motion version: %s", version)
                return version
    
    logger.debug("Motion not found or version not detectable")
    return None


def detect_ffmpeg_version() -> Optional[str]:
    """
    Detect FFmpeg version if installed.
    
    Returns:
        Version string (e.g., "6.1.1") or None if not found.
    """
    output = _run_command(["ffmpeg", "-version"])
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
    
    logger.debug("FFmpeg not found or version not detectable")
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
