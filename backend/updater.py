# File Version: 1.2.0
"""
GitHub Update Module for Motion Frontend.

This module provides functionality to check for updates from GitHub,
download and apply new versions of the application.

Supports two update modes:
- Release updates: From official GitHub releases (stable)
- Source updates: From the main branch (development/latest)

After update, automatically runs the installer repair mode on Linux
to ensure all dependencies (MediaMTX, etc.) are properly installed.

Repository: https://github.com/sn8k/Mme
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# GitHub repository configuration
GITHUB_OWNER = "sn8k"
GITHUB_REPO = "Mme"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RELEASES_URL = f"{GITHUB_API_URL}/releases"
GITHUB_DEFAULT_BRANCH = "main"
GITHUB_SOURCE_ZIP_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_DEFAULT_BRANCH}.zip"

# Project root (where the updater should operate)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class SourceInfo:
    """Information about the source code (main branch)."""
    branch: str
    commit_sha: str
    commit_message: str
    commit_date: str
    html_url: str
    zipball_url: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "commit_message": self.commit_message,
            "commit_date": self.commit_date,
            "html_url": self.html_url,
            "zipball_url": self.zipball_url,
        }


@dataclass
class ReleaseInfo:
    """Information about a GitHub release."""
    tag_name: str
    name: str
    body: str  # Release notes/changelog
    published_at: str
    html_url: str
    zipball_url: str
    tarball_url: str
    prerelease: bool
    draft: bool
    
    @property
    def version(self) -> str:
        """Extract version number from tag name (remove 'v' prefix if present)."""
        tag = self.tag_name
        if tag.startswith("v"):
            return tag[1:]
        return tag
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tag_name": self.tag_name,
            "version": self.version,
            "name": self.name,
            "body": self.body,
            "published_at": self.published_at,
            "html_url": self.html_url,
            "zipball_url": self.zipball_url,
            "prerelease": self.prerelease,
        }


@dataclass
class UpdateCheckResult:
    """Result of checking for updates."""
    current_version: str
    latest_version: Optional[str]
    update_available: bool
    latest_release: Optional[ReleaseInfo]
    error: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "latest_release": self.latest_release.to_dict() if self.latest_release else None,
            "error": self.error,
        }


@dataclass
class UpdateResult:
    """Result of an update operation."""
    success: bool
    message: str
    old_version: Optional[str]
    new_version: Optional[str]
    requires_restart: bool
    error: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "message": self.message,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "requires_restart": self.requires_restart,
            "error": self.error,
        }


def parse_version(version_str: str) -> Tuple[int, int, int, str]:
    """
    Parse a version string into comparable components.
    
    Supports formats like: 1.0.0, 1.0.0a, v1.2.3, 2.0.1b
    
    Returns (major, minor, patch, suffix)
    """
    version = version_str.strip()
    if version.startswith("v"):
        version = version[1:]
    
    # Extract suffix (letter at the end)
    suffix = ""
    if version and version[-1].isalpha():
        suffix = version[-1]
        version = version[:-1]
    
    parts = version.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        major, minor, patch = 0, 0, 0
    
    return (major, minor, patch, suffix)


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    
    Returns:
        -1 if v1 < v2
         0 if v1 == v2
         1 if v1 > v2
    """
    parsed1 = parse_version(v1)
    parsed2 = parse_version(v2)
    
    # Compare numeric parts
    for i in range(3):
        if parsed1[i] < parsed2[i]:
            return -1
        if parsed1[i] > parsed2[i]:
            return 1
    
    # Compare suffix (empty suffix is greater than any letter suffix)
    if parsed1[3] == parsed2[3]:
        return 0
    if parsed1[3] == "":
        return 1
    if parsed2[3] == "":
        return -1
    return -1 if parsed1[3] < parsed2[3] else 1


def get_current_version() -> str:
    """Get the current version from CHANGELOG.md."""
    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    try:
        with changelog_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("## "):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
    except FileNotFoundError:
        logger.warning("CHANGELOG.md not found at %s", changelog_path)
    return "0.0.0"


def get_github_headers() -> Dict[str, str]:
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"MotionFrontend/{get_current_version()}",
    }
    # Check for GitHub token in environment (optional, increases rate limit)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def fetch_latest_release(include_prereleases: bool = False) -> Optional[ReleaseInfo]:
    """
    Fetch the latest release from GitHub.
    
    Args:
        include_prereleases: If True, include prerelease versions.
        
    Returns:
        ReleaseInfo for the latest release, or None if unavailable.
    """
    try:
        if include_prereleases:
            # Get all releases and filter
            response = requests.get(
                GITHUB_RELEASES_URL,
                headers=get_github_headers(),
                timeout=15
            )
        else:
            # Get only the latest stable release
            response = requests.get(
                f"{GITHUB_RELEASES_URL}/latest",
                headers=get_github_headers(),
                timeout=15
            )
        
        response.raise_for_status()
        
        if include_prereleases:
            releases = response.json()
            if not releases:
                return None
            data = releases[0]  # First (most recent) release
        else:
            data = response.json()
        
        return ReleaseInfo(
            tag_name=data.get("tag_name", ""),
            name=data.get("name", ""),
            body=data.get("body", ""),
            published_at=data.get("published_at", ""),
            html_url=data.get("html_url", ""),
            zipball_url=data.get("zipball_url", ""),
            tarball_url=data.get("tarball_url", ""),
            prerelease=data.get("prerelease", False),
            draft=data.get("draft", False),
        )
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.info("No releases found for repository %s/%s", GITHUB_OWNER, GITHUB_REPO)
            return None
        logger.error("HTTP error fetching releases: %s", e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Network error fetching releases: %s", e)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Error parsing release data: %s", e)
        return None


def check_for_updates(include_prereleases: bool = False) -> UpdateCheckResult:
    """
    Check if an update is available.
    
    Args:
        include_prereleases: If True, include prerelease versions.
        
    Returns:
        UpdateCheckResult with update information.
    """
    current_version = get_current_version()
    logger.info("Current version: %s", current_version)
    
    try:
        latest_release = fetch_latest_release(include_prereleases)
        
        if not latest_release:
            return UpdateCheckResult(
                current_version=current_version,
                latest_version=None,
                update_available=False,
                latest_release=None,
                error="No releases found on GitHub",
            )
        
        latest_version = latest_release.version
        update_available = compare_versions(current_version, latest_version) < 0
        
        logger.info("Latest version: %s, Update available: %s", latest_version, update_available)
        
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=latest_version,
            update_available=update_available,
            latest_release=latest_release,
            error=None,
        )
        
    except Exception as e:
        logger.exception("Error checking for updates")
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=None,
            update_available=False,
            latest_release=None,
            error=str(e),
        )


def download_release(release: ReleaseInfo, target_dir: Path) -> Optional[Path]:
    """
    Download a release archive from GitHub.
    
    Args:
        release: The release to download.
        target_dir: Directory to save the downloaded file.
        
    Returns:
        Path to the downloaded archive, or None on failure.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"release-{release.version}.zip"
    
    logger.info("Downloading release %s from %s", release.version, release.zipball_url)
    
    try:
        response = requests.get(
            release.zipball_url,
            headers=get_github_headers(),
            timeout=120,
            stream=True
        )
        response.raise_for_status()
        
        with archive_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info("Downloaded release to %s", archive_path)
        return archive_path
        
    except requests.exceptions.RequestException as e:
        logger.error("Error downloading release: %s", e)
        return None


def extract_release(archive_path: Path, target_dir: Path) -> Optional[Path]:
    """
    Extract a release archive.
    
    Args:
        archive_path: Path to the archive file.
        target_dir: Directory to extract to.
        
    Returns:
        Path to the extracted directory, or None on failure.
    """
    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            # GitHub zipball has a top-level directory like "owner-repo-hash/"
            # Find it and extract
            top_dirs = {name.split('/')[0] for name in zf.namelist() if '/' in name}
            if len(top_dirs) == 1:
                top_dir = top_dirs.pop()
            else:
                top_dir = None
            
            zf.extractall(target_dir)
            
            if top_dir:
                extracted_path = target_dir / top_dir
            else:
                extracted_path = target_dir
            
            logger.info("Extracted release to %s", extracted_path)
            return extracted_path
            
    except zipfile.BadZipFile as e:
        logger.error("Invalid archive: %s", e)
        return None
    except Exception as e:
        logger.error("Error extracting release: %s", e)
        return None


def backup_current_installation(backup_dir: Path) -> bool:
    """
    Create a backup of the current installation.
    
    Args:
        backup_dir: Directory to store the backup.
        
    Returns:
        True on success, False on failure.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = backup_dir / backup_name
    
    try:
        # Backup important directories
        dirs_to_backup = ["backend", "static", "templates"]
        files_to_backup = ["requirements.txt", "CHANGELOG.md", "README.md"]
        
        backup_path.mkdir(parents=True, exist_ok=True)
        
        for dir_name in dirs_to_backup:
            src = PROJECT_ROOT / dir_name
            if src.exists():
                shutil.copytree(src, backup_path / dir_name)
        
        for file_name in files_to_backup:
            src = PROJECT_ROOT / file_name
            if src.exists():
                shutil.copy2(src, backup_path / file_name)
        
        # Don't backup config - keep user settings
        logger.info("Created backup at %s", backup_path)
        return True
        
    except Exception as e:
        logger.error("Error creating backup: %s", e)
        return False


def apply_update(extracted_path: Path) -> bool:
    """
    Apply an extracted update to the current installation.
    
    Args:
        extracted_path: Path to the extracted release.
        
    Returns:
        True on success, False on failure.
    """
    try:
        # Directories to update (skip config to preserve user settings)
        dirs_to_update = ["backend", "static", "templates", "docs", "scripts", "TODOs"]
        files_to_update = ["requirements.txt", "CHANGELOG.md", "README.md", "agents.md"]
        
        for dir_name in dirs_to_update:
            src = extracted_path / dir_name
            dst = PROJECT_ROOT / dir_name
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                logger.info("Updated directory: %s", dir_name)
        
        for file_name in files_to_update:
            src = extracted_path / file_name
            dst = PROJECT_ROOT / file_name
            if src.exists():
                shutil.copy2(src, dst)
                logger.info("Updated file: %s", file_name)
        
        return True
        
    except Exception as e:
        logger.error("Error applying update: %s", e)
        return False


def install_requirements() -> bool:
    """
    Install/update Python requirements after an update.
    
    Returns:
        True on success, False on failure.
    """
    requirements_path = PROJECT_ROOT / "requirements.txt"
    if not requirements_path.exists():
        logger.warning("requirements.txt not found, skipping pip install")
        return True
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_path), "--quiet"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            logger.info("Successfully installed requirements")
            return True
        else:
            logger.error("pip install failed: %s", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("pip install timed out")
        return False
    except Exception as e:
        logger.error("Error installing requirements: %s", e)
        return False


def run_repair() -> Tuple[bool, str]:
    """
    Run the installer repair script on Linux to fix dependencies.
    
    This function runs the install_motion_frontend.sh script in repair mode
    to ensure all dependencies (MediaMTX, system packages, etc.) are installed.
    Only runs on Linux (Raspberry Pi OS).
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if platform.system() != "Linux":
        logger.info("Repair skipped: not running on Linux")
        return True, "Repair skipped (not Linux)"
    
    installer_path = PROJECT_ROOT / "scripts" / "install_motion_frontend.sh"
    
    if not installer_path.exists():
        logger.warning("Installer script not found: %s", installer_path)
        return False, f"Installer script not found: {installer_path}"
    
    try:
        logger.info("=" * 60)
        logger.info("POST-UPDATE REPAIR: Starting automatic repair...")
        logger.info("Running: %s --repair", installer_path)
        logger.info("=" * 60)
        
        # Run the repair script
        result = subprocess.run(
            ["bash", str(installer_path), "--repair"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes timeout
            cwd=str(PROJECT_ROOT)
        )
        
        # Log the output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    logger.info("[REPAIR] %s", line)
        
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    logger.warning("[REPAIR STDERR] %s", line)
        
        if result.returncode == 0:
            logger.info("=" * 60)
            logger.info("POST-UPDATE REPAIR: Completed successfully")
            logger.info("=" * 60)
            return True, "Repair completed successfully"
        else:
            logger.error("=" * 60)
            logger.error("POST-UPDATE REPAIR: Failed with exit code %d", result.returncode)
            logger.error("=" * 60)
            return False, f"Repair failed with exit code {result.returncode}"
            
    except subprocess.TimeoutExpired:
        logger.error("POST-UPDATE REPAIR: Timed out after 10 minutes")
        return False, "Repair timed out"
    except Exception as e:
        logger.exception("POST-UPDATE REPAIR: Unexpected error")
        return False, f"Repair error: {str(e)}"


async def perform_update(include_prereleases: bool = False, auto_restart: bool = False) -> UpdateResult:
    """
    Perform a full update from GitHub.
    
    Args:
        include_prereleases: If True, include prerelease versions.
        auto_restart: If True, restart the server after update.
        
    Returns:
        UpdateResult with the operation outcome.
    """
    current_version = get_current_version()
    
    # Check for updates
    check_result = check_for_updates(include_prereleases)
    
    if check_result.error:
        return UpdateResult(
            success=False,
            message=f"Failed to check for updates: {check_result.error}",
            old_version=current_version,
            new_version=None,
            requires_restart=False,
            error=check_result.error,
        )
    
    if not check_result.update_available:
        return UpdateResult(
            success=True,
            message=f"Already running latest version ({current_version})",
            old_version=current_version,
            new_version=current_version,
            requires_restart=False,
            error=None,
        )
    
    release = check_result.latest_release
    if not release:
        return UpdateResult(
            success=False,
            message="No release information available",
            old_version=current_version,
            new_version=None,
            requires_restart=False,
            error="No release found",
        )
    
    new_version = release.version
    logger.info("Starting update from %s to %s", current_version, new_version)
    
    # Create temp directory for update
    temp_dir = Path(tempfile.mkdtemp(prefix="mme_update_"))
    
    try:
        # Create backup
        backup_dir = PROJECT_ROOT / "backups"
        if not backup_current_installation(backup_dir):
            logger.warning("Backup failed, proceeding with update anyway")
        
        # Download release
        archive_path = download_release(release, temp_dir)
        if not archive_path:
            return UpdateResult(
                success=False,
                message="Failed to download update",
                old_version=current_version,
                new_version=new_version,
                requires_restart=False,
                error="Download failed",
            )
        
        # Extract release
        extracted_path = extract_release(archive_path, temp_dir)
        if not extracted_path:
            return UpdateResult(
                success=False,
                message="Failed to extract update archive",
                old_version=current_version,
                new_version=new_version,
                requires_restart=False,
                error="Extraction failed",
            )
        
        # Apply update
        if not apply_update(extracted_path):
            return UpdateResult(
                success=False,
                message="Failed to apply update",
                old_version=current_version,
                new_version=new_version,
                requires_restart=True,  # Partial update may require restart
                error="Update application failed",
            )
        
        # Install requirements (run in thread to not block)
        loop = asyncio.get_event_loop()
        pip_success = await loop.run_in_executor(None, install_requirements)
        
        if not pip_success:
            logger.warning("pip install failed, but files were updated")
        
        # Run repair on Linux to ensure dependencies are installed (MediaMTX, etc.)
        repair_success, repair_message = await loop.run_in_executor(None, run_repair)
        if not repair_success:
            logger.warning("Post-update repair encountered issues: %s", repair_message)
        
        return UpdateResult(
            success=True,
            message=f"Successfully updated from {current_version} to {new_version}. {repair_message}. Please restart the server.",
            old_version=current_version,
            new_version=new_version,
            requires_restart=True,
            error=None,
        )
        
    except Exception as e:
        logger.exception("Unexpected error during update")
        return UpdateResult(
            success=False,
            message=f"Unexpected error: {str(e)}",
            old_version=current_version,
            new_version=new_version,
            requires_restart=False,
            error=str(e),
        )
        
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# Singleton updater instance
_updater_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None
_update_in_progress = False


async def get_update_status() -> Dict[str, Any]:
    """Get current update status."""
    global _update_in_progress
    
    return {
        "update_in_progress": _update_in_progress,
        "current_version": get_current_version(),
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }


async def trigger_update_check(include_prereleases: bool = False) -> UpdateCheckResult:
    """
    Trigger an update check (async wrapper).
    
    Args:
        include_prereleases: If True, include prerelease versions.
        
    Returns:
        UpdateCheckResult with update information.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_for_updates, include_prereleases)


async def trigger_update(include_prereleases: bool = False) -> UpdateResult:
    """
    Trigger an update (async).
    
    Args:
        include_prereleases: If True, include prerelease versions.
        
    Returns:
        UpdateResult with the operation outcome.
    """
    global _update_in_progress
    
    if _update_in_progress:
        return UpdateResult(
            success=False,
            message="An update is already in progress",
            old_version=get_current_version(),
            new_version=None,
            requires_restart=False,
            error="Update in progress",
        )
    
    try:
        _update_in_progress = True
        return await perform_update(include_prereleases)
    finally:
        _update_in_progress = False


# ============================================================================
# Source (Branch) Update Functions
# ============================================================================

def fetch_branch_info(branch: str = GITHUB_DEFAULT_BRANCH) -> Optional[SourceInfo]:
    """
    Fetch information about the latest commit on a branch.
    
    Args:
        branch: The branch name to fetch info for.
        
    Returns:
        SourceInfo for the branch, or None if unavailable.
    """
    try:
        # Get branch info
        response = requests.get(
            f"{GITHUB_API_URL}/branches/{branch}",
            headers=get_github_headers(),
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        
        commit = data.get("commit", {})
        commit_data = commit.get("commit", {})
        
        return SourceInfo(
            branch=branch,
            commit_sha=commit.get("sha", "")[:7],  # Short SHA
            commit_message=commit_data.get("message", "").split("\n")[0][:100],  # First line, truncated
            commit_date=commit_data.get("committer", {}).get("date", ""),
            html_url=commit.get("html_url", f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/tree/{branch}"),
            zipball_url=f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{branch}.zip",
        )
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.info("Branch %s not found for repository %s/%s", branch, GITHUB_OWNER, GITHUB_REPO)
            return None
        logger.error("HTTP error fetching branch info: %s", e)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Network error fetching branch info: %s", e)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Error parsing branch data: %s", e)
        return None


def check_source_updates(branch: str = GITHUB_DEFAULT_BRANCH) -> Dict[str, Any]:
    """
    Check source code info for a branch.
    
    Args:
        branch: The branch name to check.
        
    Returns:
        Dictionary with source information.
    """
    current_version = get_current_version()
    logger.info("Checking source updates for branch: %s", branch)
    
    try:
        source_info = fetch_branch_info(branch)
        
        if not source_info:
            return {
                "current_version": current_version,
                "branch": branch,
                "source_info": None,
                "error": f"Branch '{branch}' not found",
            }
        
        return {
            "current_version": current_version,
            "branch": branch,
            "source_info": source_info.to_dict(),
            "error": None,
        }
        
    except Exception as e:
        logger.exception("Error checking source updates")
        return {
            "current_version": current_version,
            "branch": branch,
            "source_info": None,
            "error": str(e),
        }


def download_source(branch: str, target_dir: Path) -> Optional[Path]:
    """
    Download source code archive from GitHub.
    
    Args:
        branch: The branch to download.
        target_dir: Directory to save the downloaded file.
        
    Returns:
        Path to the downloaded archive, or None on failure.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"source-{branch}.zip"
    
    download_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{branch}.zip"
    logger.info("Downloading source from branch %s: %s", branch, download_url)
    
    try:
        response = requests.get(
            download_url,
            headers=get_github_headers(),
            timeout=120,
            stream=True
        )
        response.raise_for_status()
        
        with archive_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info("Downloaded source to %s", archive_path)
        return archive_path
        
    except requests.exceptions.RequestException as e:
        logger.error("Error downloading source: %s", e)
        return None


async def perform_source_update(branch: str = GITHUB_DEFAULT_BRANCH) -> UpdateResult:
    """
    Perform an update from source code (branch).
    
    Args:
        branch: The branch to update from.
        
    Returns:
        UpdateResult with the operation outcome.
    """
    current_version = get_current_version()
    
    # Get branch info
    source_info = fetch_branch_info(branch)
    if not source_info:
        return UpdateResult(
            success=False,
            message=f"Failed to fetch branch '{branch}' info",
            old_version=current_version,
            new_version=None,
            requires_restart=False,
            error=f"Branch '{branch}' not found or inaccessible",
        )
    
    logger.info("Starting source update from branch %s (commit: %s)", branch, source_info.commit_sha)
    
    # Create temp directory for update
    temp_dir = Path(tempfile.mkdtemp(prefix="mme_source_update_"))
    
    try:
        # Create backup
        backup_dir = PROJECT_ROOT / "backups"
        if not backup_current_installation(backup_dir):
            logger.warning("Backup failed, proceeding with update anyway")
        
        # Download source
        archive_path = download_source(branch, temp_dir)
        if not archive_path:
            return UpdateResult(
                success=False,
                message="Failed to download source code",
                old_version=current_version,
                new_version=None,
                requires_restart=False,
                error="Download failed",
            )
        
        # Extract source
        extracted_path = extract_release(archive_path, temp_dir)
        if not extracted_path:
            return UpdateResult(
                success=False,
                message="Failed to extract source archive",
                old_version=current_version,
                new_version=None,
                requires_restart=False,
                error="Extraction failed",
            )
        
        # Apply update
        if not apply_update(extracted_path):
            return UpdateResult(
                success=False,
                message="Failed to apply source update",
                old_version=current_version,
                new_version=None,
                requires_restart=True,  # Partial update may require restart
                error="Update application failed",
            )
        
        # Install requirements (run in thread to not block)
        loop = asyncio.get_event_loop()
        pip_success = await loop.run_in_executor(None, install_requirements)
        
        if not pip_success:
            logger.warning("pip install failed, but files were updated")
        
        # Run repair on Linux to ensure dependencies are installed (MediaMTX, etc.)
        repair_success, repair_message = await loop.run_in_executor(None, run_repair)
        if not repair_success:
            logger.warning("Post-update repair encountered issues: %s", repair_message)
        
        # Get new version after update
        new_version = get_current_version()
        
        return UpdateResult(
            success=True,
            message=f"Successfully updated from source ({branch}@{source_info.commit_sha}). {repair_message}. Please restart the server.",
            old_version=current_version,
            new_version=new_version,
            requires_restart=True,
            error=None,
        )
        
    except Exception as e:
        logger.exception("Unexpected error during source update")
        return UpdateResult(
            success=False,
            message=f"Unexpected error: {str(e)}",
            old_version=current_version,
            new_version=None,
            requires_restart=False,
            error=str(e),
        )
        
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


async def trigger_source_update(branch: str = GITHUB_DEFAULT_BRANCH) -> UpdateResult:
    """
    Trigger a source update (async).
    
    Args:
        branch: The branch to update from.
        
    Returns:
        UpdateResult with the operation outcome.
    """
    global _update_in_progress
    
    if _update_in_progress:
        return UpdateResult(
            success=False,
            message="An update is already in progress",
            old_version=get_current_version(),
            new_version=None,
            requires_restart=False,
            error="Update in progress",
        )
    
    try:
        _update_in_progress = True
        return await perform_source_update(branch)
    finally:
        _update_in_progress = False


async def trigger_source_check(branch: str = GITHUB_DEFAULT_BRANCH) -> Dict[str, Any]:
    """
    Trigger a source check (async wrapper).
    
    Args:
        branch: The branch to check.
        
    Returns:
        Dictionary with source information.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_source_updates, branch)