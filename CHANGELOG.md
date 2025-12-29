<!-- File Version: 0.35.1 -->
# Changelog

## 0.35.1 - 2025-12-29
### Bug Fixes
- **FIXED**: Toast notifications no longer overlap when multiple appear rapidly.
- **IMPROVED**: Motion/FFmpeg version detection now searches multiple common paths (`/usr/bin/`, `/usr/local/bin/`, `/opt/`, `/snap/bin/`).
- **IMPROVED**: Motion version detection uses multiple regex patterns to handle different output formats.

### File Version Updates
- system_info.py: v0.1.0 → v0.2.0
- ui.css: v0.3.0 → v0.3.1
- CHANGELOG.md: v0.35.0 → v0.35.1

## 0.35.0 - 2025-12-29
### General Settings Improvements
- **NEW**: Motion version detection (via `motion -h` or `motion --version`).
- **NEW**: FFmpeg version detection and display in General Settings.
- **NEW**: `system_info.py` module for detecting system software versions.
- **NEW**: Async update status check - displays source/release updates available in settings.
- **CHANGED**: Update status field shows: "🔧 Source disponible" (priority) or "📦 X.Y.Z disponible".

### System Controls
- **NEW**: "Redémarrer le service" button with confirmation modal (Linux systemd only).
- **NEW**: `ServiceRestartHandler` endpoint (`POST /api/service/restart/`).
- **NEW**: Auto-reconnection and page reload after service restart.
- **CHANGED**: Hostname defaults to devicekey in lowercase if Meeting is configured.

### Logging Improvements
- **NEW**: "📥 Télécharger le log" button in Logging section.
- **NEW**: `LogDownloadHandler` endpoint (`GET /api/logs/download/`).
- **NEW**: Log files downloaded with timestamp in filename.
- **NEW**: Startup banner in logs: `=========== Mme vX.Y.Z starting ===========`.

### Installer Updates
- **CHANGED**: Default hostname set from devicekey (lowercase) during installation.

### File Version Updates
- system_info.py: v0.1.0 (NEW)
- config_store.py: v0.25.0 → v0.26.0
- handlers.py: v0.25.0 → v0.26.0
- server.py: v0.16.0 → v0.18.0
- main.js: v0.32.0 → v0.33.0
- main.css: v0.23.0 → v0.24.0
- install_motion_frontend.sh: v1.3.0 → v1.4.0
- CHANGELOG.md: v0.34.0 → v0.35.0

## 0.34.0 - 2025-12-29
### Dynamic Version Detection
- **FIXED**: Frontend version now reads dynamically from CHANGELOG.md on each request instead of being cached at server startup.
- **CHANGED**: VersionHandler uses `updater.get_current_version()` for live version retrieval.
- **CHANGED**: ConfigStore now uses a `frontend_version` property that reads dynamically instead of a hardcoded `_frontend_version` attribute.
- **REMOVED**: Hardcoded `self._frontend_version = "0.24.0"` in ConfigStore.

### Improved Update UX - Server Restart Handling
- **NEW**: Automatic retry mechanism when server restarts during update.
- **NEW**: Visual feedback during server restart: "Server is restarting... Please wait"
- **NEW**: Countdown display showing retry progress (1/30, 2/30, etc.)
- **NEW**: Automatic page reload when server comes back online after update.
- **NEW**: "Reload Page" button if server doesn't respond within timeout.
- **FIXED**: "Failed to fetch" error no longer shown when server restarts during update.
- **CHANGED**: Network errors during update are now handled gracefully with restart detection.

### CSS Enhancements
- **NEW**: `.progress-bar-fill.warning` style for intermediate states (amber gradient).
- **NEW**: `.restart-notice` styling for server restart messages.
- **NEW**: `#retryProgress` styling for retry countdown display.

### File Version Updates
- handlers.py: v0.24.0 → v0.25.0
- config_store.py: v0.24.0 → v0.25.0
- main.js: v0.31.0 → v0.32.0
- main.css: v0.22.0 → v0.23.0
- CHANGELOG.md: v0.33.0 → v0.34.0

## 0.33.0 - 2025-12-29
### Dynamic Camera Capabilities Detection
- **NEW**: Automatic detection of supported camera resolutions from device.
- **NEW**: Detection of all available camera controls (brightness, contrast, saturation, gain, exposure, white balance, etc.).
- **NEW**: Cross-platform support for camera controls:
  - **Linux**: V4L2 controls via `v4l2-ctl --list-ctrls-menus`
  - **Windows**: OpenCV/DirectShow property detection
- **NEW**: Real-time control adjustment - changes are applied immediately to the camera.
- **NEW**: Reset button on each control to restore default value.
- **NEW**: Support for all V4L2 control types: int (slider), bool (switch), menu (dropdown).

### UI Enhancements
- **NEW**: "Détecter" button in Video Parameters section to detect available resolutions.
- **NEW**: "Détecter les contrôles" button in Image section for advanced camera controls.
- **NEW**: Dynamic controls display with range sliders, switches, and dropdown menus.
- **CHANGED**: Image section now has basic controls (brightness, contrast, saturation) plus an "Advanced Controls" subsection.

### API Changes
- **NEW**: `GET /api/cameras/controls/<device_path>` - Get available controls for a camera.
- **NEW**: `POST /api/cameras/controls/<device_path>` - Set a camera control value.
- **EXISTING**: `GET /api/cameras/capabilities/<device_path>` - Now properly used by frontend for resolution detection.

### File Version Updates
- camera_detector.py: v0.1.0 → v0.2.0
- handlers.py: v0.23.0 → v0.24.0
- server.py: v0.15.0 → v0.16.0
- config_store.py: v0.23.0 → v0.24.0
- main.js: v0.30.0 → v0.31.0
- main.css: v0.21.0 → v0.22.0
- CHANGELOG.md: v0.32.0 → v0.33.0

## 0.32.0 - 2025-12-29
### Repair Function for Raspberry Pi Installer
- **NEW**: `--repair` option to verify and fix installation integrity.
- **NEW**: Automated checks for:
  - Installation directory and subdirectories (backend, static, templates, config, logs)
  - System user and group existence and group memberships
  - Python virtual environment and dependencies
  - systemd service file and enabled status
  - File and directory permissions
  - Configuration files presence
  - Meeting configuration (without burning tokens)
- **NEW**: Automatic fix for minor issues (missing directories, permissions, group memberships).
- **NEW**: Reinstallation offer when installation is too damaged to repair.
- **NEW**: Configuration preservation during reinstallation from repair mode.
- **CHANGED**: Repair mode validates Meeting credentials without consuming tokens.

### Installation Commands
```bash
# Repair existing installation
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --repair
```

### File Version Updates
- install_motion_frontend.sh: v1.2.3 → v1.3.0
- CHANGELOG.md: v0.31.0 → v0.32.0

## 0.31.0 - 2025-12-29
### Meeting Service Validation
- **NEW**: Meeting credentials validation against server before installation.
- **NEW**: Automatic token consumption (flash-request) on successful validation.
- **NEW**: Detailed error messages for invalid device key, wrong token code, or no tokens available.
- **CHANGED**: Meeting server URL is now fixed (`https://meeting.ygsoft.fr`) and cannot be changed.
- **REMOVED**: `--server-url` option removed from installer.
- **CHANGED**: Installation aborts if Meeting validation fails (no tokens, invalid credentials).

### Installation Flow
- Device key and token code are validated against Meeting API before proceeding.
- A token is consumed (`POST /api/devices/{device_key}/flash-request`) upon successful validation.
- Clear error messages explain how to obtain more tokens if none are available.

### File Version Updates
- install_motion_frontend.sh: v1.1.0 → v1.2.0
- CHANGELOG.md: v0.30.0 → v0.31.0

## 0.30.0 - 2025-12-29
### Raspberry Pi OS Installer
- **NEW**: Complete shell installer for Raspberry Pi OS (Debian Trixie).
- **NEW**: One-liner installation command via curl from GitHub.
- **NEW**: `--branch` option to select installation branch interactively.
- **NEW**: `--uninstall` option for complete removal.
- **NEW**: `--update` option to update existing installation.
- **NEW**: Automatic service user and group creation (`motion-frontend`).
- **NEW**: User automatically added to video, audio, gpio, i2c, spi groups.
- **NEW**: systemd service creation with security hardening.
- **NEW**: Python virtual environment setup in `/opt/motion-frontend`.
- **NEW**: Automatic dependencies installation (Python, ffmpeg, opencv, etc.).
- **NEW**: Configuration backup and restore during updates.
- **NEW**: Colored terminal output with progress indicators.

### Meeting Service Configuration
- **NEW**: `--device-key` option to set Meeting device key during installation.
- **NEW**: `--token` option to set Meeting token code during installation.
- **NEW**: `--skip-meeting` option to skip Meeting configuration prompt.
- **NEW**: Interactive prompt for Meeting configuration if not provided via CLI.

### Installation Commands
```bash
# Quick install (main branch)
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash

# Install with branch selection
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --branch

# Install with Meeting configuration
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- \
  --device-key YOUR_KEY --token YOUR_TOKEN

# Uninstall
curl -sSL https://raw.githubusercontent.com/sn8k/Mme/main/scripts/install_motion_frontend.sh | sudo bash -s -- --uninstall
```

### File Version Updates
- **NEW**: install_motion_frontend.sh: v1.2.0
- CHANGELOG.md: v0.29.0 → v0.31.0
- TECHNICAL_DOCUMENTATION.md: v1.17.0 → v1.18.0

## 0.29.0 - 2025-12-29
### Update from Source Feature
- **NEW**: "Update from Source" option to update directly from the main branch (development version).
- **NEW**: Tabbed update modal with "Releases" and "Source (Dev)" tabs.
- **NEW**: Source info display showing branch name, latest commit SHA, commit message, and date.
- **NEW**: Warning notice for source updates about untested features.
- **NEW**: API actions `check_source` and `update_source` in `/api/update/` endpoint.

### Backend Implementation
- Updated `updater.py` (v1.0.0 → v1.1.0) with source update functions:
  - `fetch_branch_info()`: Get latest commit info from a branch.
  - `check_source_updates()`: Check source code info for a branch.
  - `download_source()`: Download source archive from branch.
  - `perform_source_update()`: Full source update workflow.
  - `trigger_source_update()`: Async wrapper for source updates.
- Updated `UpdateHandler` to support `check_source` and `update_source` actions.
- Added query parameter `source=true` for GET requests to check source info.

### Frontend Implementation
- Redesigned update modal with tab interface for releases vs source.
- Added source info display with commit details and warning notice.
- Updated `performUpdate()` to handle both release and source updates.
- Added CSS styles for tabs, source notices, and warning buttons.
- Added i18n translations for source update strings (EN/FR).

### File Version Updates
- updater.py: v1.0.0 → v1.1.0
- handlers.py: v0.22.0 → v0.23.0
- main.js: v0.29.0 → v0.30.0
- main.css: v0.20.0 → v0.21.0
- motion_frontend.en.json: updated
- motion_frontend.fr.json: updated

## 0.28.0 - 2025-12-29
### GitHub Update Feature
- **NEW**: Full GitHub update functionality via UI button "Update".
- **NEW**: `/api/update/` endpoint to check for updates and perform updates from GitHub.
- **NEW**: Update modal showing current version, latest version, release notes, and progress.
- **NEW**: Automatic backup creation before applying updates.
- **NEW**: Version comparison supporting semantic versioning with letter suffixes (e.g., 1.0.0a).
- **NEW**: Support for `GITHUB_TOKEN` environment variable to increase API rate limits.
- **NEW**: Update progress indicator with download/install status.

### Backend Implementation
- Added `updater.py` module with full GitHub release management:
  - `check_for_updates()`: Check for new releases from GitHub.
  - `perform_update()`: Download, extract, and apply updates.
  - `backup_current_installation()`: Create backup before update.
  - `install_requirements()`: Run pip install after update.
- Added `UpdateHandler` in handlers.py with GET (check) and POST (update) actions.
- Added `/api/update/` route in server.py.
- GitHub repository: https://github.com/sn8k/Mme

### Frontend Implementation
- Updated `triggerUpdate()` to display update modal with version info.
- Added `showUpdateModal()` for rich update UI with release notes.
- Added `performUpdate()` for async update execution with progress.
- Added CSS styles for update modal (`.version-info`, `.update-status`, `.release-notes`, `.progress-bar`).
- Added i18n translations for update-related strings (EN/FR).

### File Version Updates
- handlers.py: v0.21.0 → v0.22.0
- server.py: v0.14.0 → v0.15.0
- main.js: v0.28.0 → v0.29.0
- main.css: v0.19.0 → v0.20.0
- motion_frontend.en.json: updated with update strings
- motion_frontend.fr.json: updated with update strings
- **NEW**: updater.py: v1.0.0

## 0.27.0 - 2025-12-29
### RTSP/MJPEG Camera Access Conflict Resolution
- **FIXED**: Preview showing "no signal" or scrambled image when RTSP is active.
- **FIXED**: Camera access conflict between FFmpeg (RTSP) and OpenCV (MJPEG) on Windows.
- **CHANGED**: MJPEG stream automatically stops when RTSP starts (releases camera for FFmpeg).
- **CHANGED**: MJPEG stream automatically restarts when RTSP is disabled.
- **NEW**: "RTSP Stream Active" placeholder image shown in preview when RTSP is running.
- **NEW**: Preview displays RTSP URL for users to connect with external client.

### Backend Implementation
- Modified `ConfigCameraHandler.post()` to stop MJPEG before starting RTSP.
- Modified `ConfigCameraHandler.post()` to restart MJPEG after stopping RTSP.
- Modified `_start_rtsp_streams_on_boot()` to stop MJPEG before RTSP auto-start.
- Modified `FrameHandler` to return SVG placeholder when RTSP is active.
- Modified `MJPEGStreamHandler` to return SVG placeholder when RTSP is active.

### File Version Updates
- handlers.py: v0.20.0 → v0.21.0
- server.py: v0.13.0 → v0.14.0

## 0.26.0 - 2025-12-29
### RTSP Auto-Start and DirectShow Device Matching
- **NEW**: RTSP streams now auto-start on server boot for cameras with `rtsp_enabled=true`.
- **FIXED**: DirectShow device name matching with special characters (e.g., `®` symbol).
- **FIXED**: Resolution fallback to 1280x720 for unsupported resolutions on Windows webcams.
- **IMPROVED**: Added FFmpeg device enumeration for exact DirectShow device name discovery.
- **IMPROVED**: Fuzzy matching between camera names and DirectShow device names using Unicode normalization.

### Backend Implementation
- Added `_start_rtsp_streams_on_boot()` function in server.py for automatic RTSP initialization.
- Added `_normalize_device_name()` method for Unicode-aware device name comparison.
- Added `_list_dshow_devices()` method to enumerate DirectShow video/audio devices via FFmpeg.
- Added `_find_matching_dshow_device()` method for fuzzy device name matching.
- Modified `_get_video_input_args()` to use detected DirectShow names and resolution fallback.

### File Version Updates
- server.py: v0.12.0 → v0.13.0
- rtsp_server.py: v0.2.0 → v0.3.0

## 0.25.0 - 2025-12-29
### RTSP Toggle Activation
- **CHANGED**: RTSP stream activation changed from start/stop buttons to enable/disable toggle.
- **NEW**: Added `rtsp_enabled` and `rtsp_audio_device` fields to CameraConfig dataclass.
- **NEW**: RTSP stream auto-starts when toggle is enabled, auto-stops when disabled.
- **NEW**: Audio device selector in RTSP section for selecting audio source per camera.
- **IMPROVED**: RTSP status display shows active/stopped state and URL when running.
- **FIXED**: Fixed audio device iteration bug in RTSPStreamHandler.
- **FIXED**: Fixed camera.device_url reference error (now uses device_settings).

### Backend Implementation
- Added `rtsp_enabled: bool = False` and `rtsp_audio_device: str = ""` to CameraConfig.
- Added `_get_audio_device_choices()` helper method to ConfigStore.
- Modified ConfigCameraHandler.post() to handle RTSP auto-start/stop on save.
- Updated save_camera_config() to persist RTSP settings.

### Frontend Implementation
- Replaced RTSP buttons with bool toggle field (`rtspEnabled`).
- Added audio device dropdown (`rtspAudioDevice`) with dynamic choices.
- Updated updateRTSPUI() to work with toggle-based UI.
- Enhanced pushConfigs() to handle RTSP response and update UI.
- Added translations for new messages (FFmpeg required, failed to start).

### File Version Updates
- config_store.py: v0.22.0 → v0.23.0
- handlers.py: v0.19.0 → v0.20.0
- main.js: v0.27.0 → v0.28.0
- motion_frontend.fr.json: v0.4.0 → v0.4.1
- motion_frontend.en.json: v0.4.0 → v0.4.1

## 0.24.1 - 2025-12-29
### RTSP UI Improvements
- **CHANGED**: Moved RTSP controls from preview area to camera configuration menu.
- **CHANGED**: Renamed "Streaming" section to "Streaming MJPEG" for clarity.
- **NEW**: Added "Streaming RTSP" section in camera configuration with inline controls.
- **IMPROVED**: RTSP controls are now camera-specific with dynamic IDs.

### File Version Updates
- config_store.py: v0.21.0 → v0.22.0
- main.js: v0.26.0 → v0.27.0
- main.html: v0.12.0 → v0.13.0
- main.css: v0.18.0 → v0.19.0

## 0.24.0 - 2025-12-29
### RTSP Streaming Server
- **NEW**: RTSP server module using FFmpeg for H.264 video + AAC audio streaming.
- **NEW**: Automatic audio muxing from linked audio device when available.
- **NEW**: Cross-platform support (Windows DirectShow, Linux V4L2/ALSA).
- **NEW**: Per-camera RTSP streams on dedicated ports (8554+).
- **NEW**: RTSP control panel in UI with start/stop buttons and URL display.
- **NEW**: Real-time status indicators (stream active, audio presence).

### Backend Implementation
- Created `backend/rtsp_server.py` with `RTSPStreamConfig`, `RTSPStreamStatus`, and `RTSPServer` class.
- FFmpeg command builder for video/audio capture and RTSP output.
- Support for multiple video codecs (libx264) and audio codecs (AAC, Opus, MP3, PCM).
- Low-latency encoding with ultrafast preset and zerolatency tune.
- Added `RTSPStatusHandler` and `RTSPStreamHandler` to handlers.py.

### API Endpoints
- `GET /api/rtsp/` - Get RTSP server status and FFmpeg availability.
- `GET /api/rtsp/<camera_id>/` - Get RTSP stream status for a camera.
- `POST /api/rtsp/<camera_id>/` - Start/stop RTSP stream (action: start|stop).

### File Version Updates
- rtsp_server.py: v0.1.0 (NEW)
- handlers.py: v0.18.0 → v0.19.0
- server.py: v0.10.0 → v0.11.0
- main.js: v0.25.0 → v0.26.0
- main.html: v0.11.0 → v0.12.0
- main.css: v0.17.0 → v0.18.0
- motion_frontend.fr.json: v0.3.0 → v0.4.0
- motion_frontend.en.json: v0.3.0 → v0.4.0

## 0.23.0 - 2025-12-29
### Audio Input Device Management
- **NEW**: Cross-platform audio input detection (Windows via PowerShell/WMI/FFmpeg, Linux via ALSA/arecord).
- **NEW**: Audio device management UI mirroring camera management pattern.
- **NEW**: Add/remove audio devices functionality with configuration persistence.
- **NEW**: Audio configuration sections with settings (sample rate, channels, bit depth, volume, codec, bitrate, noise reduction, linked camera).
- **NEW**: Audio device filter patterns to hide system/virtual devices.
- **NEW**: Complete i18n support for audio features (FR/EN).

### Backend Implementation
- Created `backend/audio_detector.py` with `DetectedAudioDevice` dataclass and `AudioDetector` class.
- Added `AudioConfig` dataclass to `config_store.py` with full audio configuration fields.
- Added audio configuration storage methods: `get_audio_devices()`, `add_audio_device()`, `remove_audio_device()`, `save_audio_config()`, `get_audio_config_sections()`.
- Added audio filter patterns management: `get_audio_filter_patterns()`, `add_audio_filter_pattern()`, `remove_audio_filter_pattern()`.
- Added 7 new Tornado handlers for audio API endpoints.

### API Endpoints
- `GET /api/audio/detect/` - Detect available audio input devices.
- `GET /api/audio/filters/` - Get audio filter patterns.
- `POST /api/audio/filters/` - Add/remove audio filter pattern.
- `GET /api/config/audio/list/` - List configured audio devices.
- `POST /api/config/audio/add/` - Add new audio device.
- `GET /api/config/audio/<id>/` - Get audio device configuration.
- `POST /api/config/audio/<id>/` - Update audio device configuration.
- `GET /api/config/audio/<id>/sections/` - Get audio config sections for UI.
- `POST /api/config/audio/<id>/delete/` - Delete audio device.

### File Version Updates
- audio_detector.py: v0.1.0 (NEW)
- config_store.py: v0.20.0 → v0.21.0
- handlers.py: v0.17.0 → v0.18.0
- server.py: v0.9.0 → v0.10.0
- main.js: v0.24.1 → v0.25.0
- main.html: v0.10.1 → v0.11.0
- main.css: v0.16.0 → v0.17.0
- motion_frontend.fr.json: v0.2.0 → v0.3.0
- motion_frontend.en.json: v0.2.0 → v0.3.0

## 0.22.5 - 2025-12-29
### UI Accordion Fix
- **Fixed**: Settings sections can now be properly collapsed/expanded.
- **Fixed**: Dynamically loaded camera config sections now have full accordion behavior.
- **Changed**: All settings sections are collapsed by default for cleaner UI.
- Added `bindAccordionButtons()` helper function for consistent accordion behavior.

### File Version Updates
- main.js: v0.24.0 → v0.24.1
- main.html: v0.10.0 → v0.10.1
- ui.js: v0.2.1 → v0.2.2

## 0.22.4 - 2025-12-29
### Stream Authentication (HTTP Basic Auth)
- **NEW**: Option to enable/disable password protection for MJPEG streams.
- **Disabled by default** for backward compatibility.
- When enabled, uses user credentials (not admin) for authentication.
- External access URL format: `http://user:password@<ip>:<port>/stream/`
- UI stream URL display shows masked password (`****`) when auth is enabled.
- Returns 401 Unauthorized with WWW-Authenticate header when credentials are missing/invalid.
- Auth is checked for both `/stream/` and `/status` endpoints.

### Implementation Details
- Added `stream_auth_enabled` field to CameraConfig and CameraStream.
- Added `get_user_credentials()` method to ConfigStore.
- HTTP Basic Auth validation in `create_mjpeg_handler()` with base64 decoding.
- Added `_check_auth()` and `_send_auth_required()` methods in MJPEG handler.

### File Version Updates
- mjpeg_server.py: v0.8.0 → v0.9.0
- config_store.py: v0.19.0 → v0.20.0
- handlers.py: v0.16.0 → v0.17.0

## 0.22.3 - 2025-12-29
### MJPEG Server Restart Fix
- **Fixed**: Server crash when saving camera config while streaming.
- HTTP server shutdown now runs in separate thread to avoid blocking.
- Added 500ms delay before restarting stream to allow port release.
- Added retry mechanism (3 attempts) when binding to MJPEG port.
- Socket created with SO_REUSEADDR before binding for faster port reuse.

### File Version Updates
- mjpeg_server.py: v0.7.0 → v0.8.0
- handlers.py: v0.15.0 → v0.16.0

## 0.22.2 - 2025-12-29
### File Logging with Rotation
- **NEW**: Logs are now written to `logs/motion_frontend.log`.
- Log file uses rotation: max 5MB per file, keeps 3 backups.
- **NEW**: UI setting "Enregistrer dans un fichier" to enable/disable file logging.
- **NEW**: UI setting "Effacer le log au démarrage" to reset log file on startup.
- Settings are persisted and read at server startup.

### File Version Updates
- server.py: v0.8.0 → v0.9.0 (file logging with RotatingFileHandler)
- config_store.py: v0.18.0 → v0.19.0 (log_to_file, log_reset_on_start settings)

## 0.22.1 - 2025-12-29
### Log Level Configuration in General Settings
- **NEW**: Added log level configuration in General Settings section.
- Available levels: DEBUG (verbose), INFO (standard), WARNING, ERROR, CRITICAL.
- Log level change is applied immediately without restart.
- Setting is persisted in configuration file.

### File Version Updates
- config_store.py: v0.17.0 → v0.18.0

## 0.22.0 - 2025-12-29
### Dedicated MJPEG Servers per Camera (Major Architecture Change)
- **NEW**: Each camera now has its own dedicated HTTP server on a configurable port.
- Camera 1 streams on port 8081 by default, Camera 2 on 8082, etc.
- External clients (VLC, Surveillance Station) should use: `http://<ip>:<mjpeg_port>/stream/`
- UI preview still uses the main Tornado server as fallback.
- Each dedicated server includes a status page at root URL.

### Implementation Details
- Added `create_mjpeg_handler()` factory function for per-camera HTTP handlers.
- Added `_start_http_server()` method to start dedicated server on camera start.
- Added `_stop_http_server()` method to cleanly shutdown server on camera stop.
- HTTP server runs in dedicated thread with SO_REUSEADDR for quick restart.
- Proper error handling for port conflicts (address already in use).

### URL Display Updates
- Stream URL now shows dedicated MJPEG port: `http://<ip>:<mjpeg_port>/stream/`
- Removed camera ID from URL path (each port serves one camera).
- Copy button copies correct URL for external clients.

### File Version Updates
- mjpeg_server.py: v0.6.0 → v0.7.0
- handlers.py: v0.14.0 → v0.15.0 (passes mjpeg_port to add_camera)
- config_store.py: v0.16.0 → v0.17.0 (URL display uses mjpeg_port)
- main.js: v0.23.2 → v0.24.0 (copyStreamUrl uses mjpeg_port)

## 0.21.6 - 2025-12-29
### Stream URL Fix (Correct Port)
- **Fixed**: Stream URL now uses actual server port (8765) instead of unused MJPEG port.
- URL format: `http://<ip>:8765/stream/<camera_id>/`
- Removed "Port MJPEG" field from streaming config (was not functional).
- Copy button now copies the working URL.

### File Version Updates
- config_store.py: v0.15.0 → v0.16.0
- main.js: v0.23.1 → v0.23.2

## 0.21.5 - 2025-12-29
### Stream URL Fix
- **Fixed**: Stream URL now displays real server IP instead of `<ip>` placeholder.
- IP is detected server-side using socket connection to ensure correct value.
- URL format simplified to `http://<ip>:<port>/stream/` (without camera ID suffix).
- Copy button now copies the correct URL with real IP address.

### File Version Updates
- config_store.py: v0.14.0 → v0.15.0
- main.js: v0.23.0 → v0.23.1

## 0.21.4 - 2025-12-29
### Config Save Fix
- **Fixed**: ValueError when saving camera config with empty numeric fields.
- Added `_safe_int()` helper function to handle empty/invalid values gracefully.
- All numeric config fields now use safe parsing with default values.

### Stream URL Display
- **Improved**: Stream URL now shows full URL with IP address and MJPEG port.
- URL format: `http://<ip>:<mjpeg_port>/stream/<camera_id>/`
- URL updates dynamically when MJPEG port is changed.
- Copy button copies the complete URL ready to paste in VLC or Surveillance Station.

### File Version Updates
- config_store.py: v0.13.0 → v0.14.0
- main.js: v0.22.0 → v0.23.0

## 0.21.3 - 2025-12-29
### Preview Display Fix
- **Fixed**: Camera preview now shows complete image instead of cropped.
- Changed CSS `object-fit` from `cover` to `contain` for preview frames.
- Text overlay is now fully visible in the preview.

### Resolution Stats Fix
- **Fixed**: Displayed resolution now shows actual stream output resolution.
- Stats now correctly show `stream_resolution` instead of `capture_resolution`.
- Added `capture_width` and `capture_height` to status for reference.

### Auto-Restart Stream on Config Change
- **New**: Stream automatically restarts when camera config is saved.
- Applies new resolution, framerate, quality, and overlay settings immediately.
- No need to manually stop/start stream after config changes.

### File Version Updates
- mjpeg_server.py: v0.5.0 → v0.5.1
- handlers.py: v0.13.0 → v0.14.0
- main.css: v0.15.0 → v0.16.0

## 0.21.2 - 2025-12-29
### Fullscreen Button Fix
- **Fixed**: Fullscreen button moved from static HTML to dynamic JS overlay.
- Button now appears next to the stop/play button in the camera overlay.
- Works in both LIVE and OFFLINE states.
- Added hover effect (blue color) for fullscreen button.

### Text Overlay Fix
- **Fixed**: Removed duplicate drawing code that caused rendering issues.
- Text overlay now renders correctly on the stream output.

### Output Resolution (stream_resolution) Implementation
- **Fixed**: `stream_resolution` setting now properly applied.
- Added `stream_width` and `stream_height` to CameraStream dataclass.
- Added `cv2.resize()` step in capture loop to resize output.
- Capture resolution (input) and stream resolution (output) are now independent.
- Handlers pass both resolutions to MJPEG server.

### Camera Capabilities Detection
- **New feature**: API endpoint to detect camera capabilities.
- New endpoint: `GET /api/cameras/capabilities/<device_path>`
- Returns: supported resolutions, current resolution, max FPS, backend.
- Tests common resolutions (QVGA to 4K UHD).
- Useful for dynamic resolution dropdown population.

### File Version Updates
- mjpeg_server.py: v0.4.0 → v0.5.0
- handlers.py: v0.12.0 → v0.13.0
- server.py: v0.7.0 → v0.8.0
- main.js: v0.21.0 → v0.22.0
- main.html: v0.9.0 → v0.10.0
- main.css: v0.14.0 → v0.15.0

## 0.21.1 - 2025-12-29
### Text Overlay Positioning Fix
- Fixed text overlay rendering beyond video stream boundaries.
- Overlay now uses actual frame dimensions (`frame.shape`) instead of camera config.
- Added bounds checking and text truncation for long text.
- Improved padding calculation for small resolutions.

### Camera Fullscreen Mode
- **New feature**: Fullscreen button on camera preview cells.
- Click the maximize icon (⛶) to enter fullscreen mode.
- ESC key or click minimize icon to exit fullscreen.
- Supports both CSS fullscreen and native browser fullscreen API.
- Stream continues playing in fullscreen mode.

### File Version Updates
- mjpeg_server.py: v0.3.0 → v0.4.0
- main.js: v0.20.0 → v0.21.0
- main.html: v0.8.0 → v0.9.0
- main.css: v0.13.0 → v0.14.0

## 0.21.0 - 2025-12-29
### Text Overlay Feature
- **New feature**: Add text overlay to video stream output.
- Camera configuration now includes "Text Overlay" section with:
  - **Left Text**: Camera Name, Timestamp, Custom Text, Capture Info, or Disabled.
  - **Right Text**: Camera Name, Timestamp, Custom Text, Capture Info, or Disabled.
  - **Text Scale**: Slider from 1 to 10 (default: 3).
- Custom text input field appears only when "Texte personnalisé" is selected.
- Overlay is rendered with black background for readability.
- Default: Left disabled, Right shows timestamp.

### Frontend Improvements
- Enhanced `evaluateDepends()` to support `key=value` syntax for conditional display.
- Custom text input fields show/hide based on selected overlay type.

### File Version Updates
- config_store.py: v0.12.0 → v0.13.0
- handlers.py: v0.11.0 → v0.12.0
- mjpeg_server.py: v0.2.0 → v0.3.0
- main.js: v0.19.0 → v0.20.0

## 0.20.0 - 2025-01-14
### User Management System
- **New feature**: Secure user management with password hashing (bcrypt).
- Added `user_manager.py` module with comprehensive user management:
  - Password hashing with bcrypt (12 rounds) or SHA256 fallback.
  - Role-based access control: ADMIN, USER, VIEWER.
  - User persistence in `config/users.json`.
  - Password migration support for legacy SHA256 hashes.
  - `must_change_password` flag for first login or admin reset.

### Password Change from UI
- Added password change button in header (lock icon).
- Modal dialog for changing password with validation.
- Current password verification before allowing changes.
- Minimum 6 characters for new passwords.
- Auto-prompt for password change if `must_change_password` is set.

### User Management API
- `GET /api/user/me/` - Get current user info.
- `POST /api/user/password/` - Change own password.
- `GET /api/users/` - List all users (admin only).
- `POST /api/users/` - Create new user (admin only).
- `DELETE /api/users/` - Delete user (admin only).
- `POST /api/users/reset-password/` - Admin password reset.
- `POST /api/users/enable/` - Enable/disable user (admin only).

### Authentication Improvements
- Replaced in-memory `_USERS` dict with `UserManager`.
- Login now uses `UserManager.authenticate()`.
- Auto-redirect to password change on first login if required.

### Dependencies
- Added bcrypt>=4.1 to requirements.txt.

### File Version Updates
- handlers.py: v0.10.0 → v0.11.0
- server.py: v0.6.0 → v0.7.0
- main.js: v0.18.0 → v0.19.0
- main.html: v0.7.0 → v0.8.0
- ui.css: v0.2.2 → v0.3.0
- requirements.txt: v1.2.0 → v1.3.0
- user_manager.py: v0.1.0 (new)

## 0.19.0 - 2025-12-28
### Meeting Configuration Simplification
- Removed Meeting server URL from frontend configuration (hardcoded to `https://meeting.ygsoft.fr`).
- Users only need to configure Device Key, Token Code, and heartbeat interval.

### Meeting Status Display Fix
- Fixed Meeting status permanently showing "--" despite successful heartbeats.
- Unified API response format: GET `/api/meeting/` now returns `service` key (same as POST).

### Enhanced Meeting Heartbeat Data
- Heartbeat now includes comprehensive device information:
  - Local IP address
  - Public IP address (fetched from external service, cached 5 minutes)
  - Hostname
  - Platform details (OS, release, machine, Python version)
  - Services ports (SSH, HTTP, VNC, MJPEG)
  - Camera list with names and stream URLs
- Added `set_callbacks()` method for dynamic camera/port information.

### File Version Updates
- config_store.py: v0.11.0 → v0.12.0
- handlers.py: v0.9.0 → v0.10.0
- meeting_service.py: v0.3.0 → v0.4.0

## 0.18.0 - 2025-12-28
### Stream URL Display
- Added dynamic stream URL display in camera streaming settings.
- URL format: `/stream/{camera_id}/` with copy button.
- Click copy button (📋) to copy full URL to clipboard.

### Meeting Status Stability
- Fixed unstable Meeting status display that flickered to "--".
- Status now persists last known state during temporary API failures.
- Prevents UI flickering when polling encounters network issues.

### File Version Updates
- config_store.py: v0.10.0 → v0.11.0
- main.js: v0.17.0 → v0.18.0
- main.css: v0.12.0 → v0.13.0

## 0.17.0 - 2025-12-28
### Meeting Service Bugfix
- Fixed error 500 when saving Meeting deviceKey/tokenCode configuration.
- Replaced obsolete `_enabled` check with `is_configured()` in `send_manual_heartbeat()`.
- Fixed auto-start logic in frontend to use `status.is_configured` instead of `config.enabled`.

### File Version Updates
- meeting_service.py: v0.2.0 → v0.3.0
- main.js: v0.16.0 → v0.17.0

## 0.16.0 - 2025-12-28
### Meeting Default URL
- Default Meeting server URL is now `https://meeting.ygsoft.fr`.
- Placeholder in UI updated to reflect the default URL.

### Remember Me Fix
- Fixed "Remember me" functionality on login page.
- Sessions are now persisted to `config/sessions.json` file.
- Sessions survive server restarts when "Remember me" is checked.
- Cookie duration remains 30 days when enabled.

### File Version Updates
- config_store.py: v0.9.0 → v0.10.0
- handlers.py: v0.8.0 → v0.9.0

## 0.15.0 - 2025-12-28
### Meeting Always-On Mode
- **Breaking change**: Meeting service now runs permanently when configured (no enable/disable toggle).
- Removed `meetingEnabled` toggle from configuration UI.
- Service auto-starts if `server_url` and `device_key` are provided.
- Extended heartbeat interval max from 300s to 3600s (1 hour).
- Status now shows "Non configuré" when URL or Device Key is missing.
- Status shows "Connexion en cours..." during initial connection.

### File Version Updates
- config_store.py: v0.8.0 → v0.9.0
- meeting_service.py: v0.1.0 → v0.2.0
- handlers.py: v0.7.0 → v0.8.0
- main.js: v0.15.0 → v0.16.0

## 0.14.0 - 2025-12-28
### Meeting API Integration
- Added full Meeting API support for device heartbeat signaling.
- New configuration section "Meeting" in settings panel:
  - **meetingServerUrl**: URL of the Meeting server
  - **meetingDeviceKey**: Unique device key for identification
  - **meetingTokenCode**: Authentication token
  - **meetingHeartbeatInterval**: Interval in seconds (10-3600)
  - **meetingStatus**: Real-time connection status indicator

### Backend Meeting Service
- New `backend/meeting_service.py` (v0.1.0):
  - Async heartbeat loop using aiohttp
  - Configurable heartbeat interval
  - Automatic IP address detection
  - Service status reporting (devices, http, ssh, vnc)
  - Error handling with retry logic
- New API endpoint `POST/GET /api/meeting/`:
  - `GET`: Get current Meeting service status
  - `POST action=start`: Start heartbeat service
  - `POST action=stop`: Stop heartbeat service
  - `POST action=heartbeat`: Send manual heartbeat (for testing)
  - `POST action=configure`: Reconfigure service with current settings

### Frontend Meeting Controls
- Meeting status indicator with color coding:
  - Green: Connected (last successful heartbeat time)
  - Red: Error with message
  - Gray: Non configuré / Démarrage
- Auto-start Meeting service on page load
- Real-time status polling every 10 seconds

### Dependencies
- Added `aiohttp>=3.9` to requirements.txt

### Documentation
- Added Meeting API documentation in TECHNICAL_DOCUMENTATION.md:
  - API endpoints section with payload examples
  - Meeting configuration parameters
  - Service workflow documentation
- Updated JSON config structure with Meeting section

### File Version Updates
- config_store.py: v0.7.0 → v0.8.0
- handlers.py: v0.6.0 → v0.7.0
- server.py: v0.5.0 → v0.6.0
- main.js: v0.14.0 → v0.15.0
- main.css: v0.11.0 → v0.12.0
- requirements.txt: v1.1.0 → v1.2.0
- TECHNICAL_DOCUMENTATION.md: v1.8.0 → v1.9.0

## 0.13.0 - 2025-12-28
### Stream Stats in Camera Overlay
- Moved FPS, resolution, and bandwidth metrics from status bar to individual camera overlays.
- Real-time stats per camera: FPS, resolution (WxH), bandwidth (Kb/s or Mb/s).
- Stats update every second via polling when streaming is active.
- Removed global status metrics from status bar (now per-camera in overlay).

### Backend Stats Tracking
- Added real-time FPS calculation in MJPEG server.
- Added bandwidth tracking (bytes sent per second).
- New fields in CameraStream: `_real_fps`, `_bandwidth_kbps`, `last_frame_size`.
- Stats are calculated over 1-second intervals for accuracy.

### UI Improvements
- New `.stream-stats` CSS class for stats display in overlay.
- Stats display: monospace font, dark background, compact layout.
- Bandwidth auto-formats to Mb/s when >= 1000 Kb/s.

### File Version Updates
- main.js: v0.13.0 → v0.14.0
- main.css: v0.10.0 → v0.11.0
- main.html: v0.6.0 → v0.7.0

## 0.12.0 - 2025-12-28
### Camera Configuration Sections Reorganization
- Separated camera input settings from streaming output settings.
- **Section "Paramètres vidéo"** now contains input/capture settings:
  - Capture resolution (resolution from camera source)
  - Capture framerate (fps from camera source)
  - Rotation
- **Section "Streaming"** now contains output settings:
  - Stream enabled toggle
  - MJPEG port
  - Stream URL (readonly)
  - Output resolution (stream_resolution)
  - Output framerate (stream_framerate) 
  - JPEG quality

### New Configuration Fields
- Added `stream_resolution` field: output resolution for MJPEG stream (default: 1280x720)
- Added `stream_framerate` field: output fps for MJPEG stream (default: 15)
- Added `jpeg_quality` field: JPEG encoding quality 10-100% (default: 80)

### Migration Note
- Existing camera configs will inherit capture resolution/framerate as default stream values.

### File Version Updates
- config_store.py: v0.6.0 → v0.7.0

## 0.11.0 - 2025-12-28
### Auto-Start Live Streaming
- Streams are now automatically started for all cameras on page load.
- New `autoStartAllStreams()` function handles batch stream initialization.

### Overlay Controls Redesign
- Clicking on a camera preview now toggles overlay visibility (not stream).
- Overlay shows play/stop controls to manage stream state.
- Stop button (⏹) in overlay to stop stream when live.
- Play button (▶) in overlay to start stream when offline.
- Full overlay background with semi-transparent dark layer.
- Added `visibleOverlays` state to track overlay visibility per camera.

### UI Improvements
- "OFFLINE" status badge for cameras not streaming.
- Larger control buttons (40px) with hover effects.
- Green highlight on play button hover, red on stop button hover.
- Smooth transitions on overlay and buttons.

### File Version Updates
- main.js: v0.12.0 → v0.13.0
- main.css: v0.9.0 → v0.10.0

## 0.10.0 - 2025-12-28
### Camera Selection & Configuration Fix
- Fixed camera configuration not displaying when selecting a camera from dropdown.
- Auto-select first camera on page load when cameras exist.
- Camera config panel now properly loads and displays settings.

### Preview Grid Improvements  
- Preview count is now user-configurable even with a single camera.
- Simple view (1) is the default for single camera, but user can override to quad/etc.
- Added `userOverridePreviewCount` state to track manual user preference.

### Stream Details Overlay
- Added visual overlay on active camera streams showing "LIVE" status badge.
- Overlay displays stream type (MJPEG) when streaming is active.
- Pulsing red "LIVE" indicator for active streams.

### File Version Updates
- main.js: v0.11.0 → v0.12.0
- main.css: v0.8.0 → v0.9.0
- main.html: v0.5.0 → v0.6.0

## 0.9.0 - 2025-12-28
### Camera Preview Improvements
- Display "Aucune caméra configurée" message when no cameras are set up.
- Auto-select simple view (1 preview) when only one camera is configured.
- Fixed camera deletion - all cameras can now be deleted including the first one.
- Empty preview slots now show a dashed placeholder instead of dummy images.

### UI Enhancements
- Improved empty state styling with dashed border and better messaging.
- Added `.empty-slot` CSS class for empty camera slots.
- Better visual feedback when no cameras are configured.

### File Version Updates
- main.js: v0.10.0 → v0.11.0
- main.css: v0.7.0 → v0.8.0

## 0.8.0 - 2025-12-28
### Camera Deletion UI Fix
- Fixed camera deletion button not enabling when selecting a camera from dropdown.
- Added `updateRemoveCameraButtonState()` function for consistent button state management.
- Remove camera button (`-`) now correctly enables/disables based on camera selection.

### File Version Updates
- main.js: v0.9.0 → v0.10.0

## 0.7.0 - 2025-12-28
### MJPEG Streaming Server
- Added MJPEG streaming server for Windows (DirectShow) and Linux (v4l2).
- New `backend/mjpeg_server.py` module (v0.1.0) with OpenCV-based capture.
- Real-time video streaming via HTTP multipart/x-mixed-replace.
- API endpoints:
  - `GET /api/mjpeg/` - Get status of all streams
  - `POST /api/mjpeg/` - Start/stop camera streams (actions: start, stop, stop_all)
  - `GET /stream/{camera_id}/` - MJPEG stream endpoint

### Stream Features
- Multi-threaded capture with per-camera threads
- Configurable resolution, framerate, and JPEG quality
- Automatic frame rate control
- Low-latency streaming with buffer size optimization
- Placeholder frame for offline cameras ("No Signal")
- Subscriber-based streaming (only encodes when clients connected)

### LivePreview Integration
- Click on any camera preview cell to start/stop streaming
- Red dot indicator (🔴) for streaming cameras
- Automatic switch between polling mode and MJPEG streaming
- Stream status persistence across page refreshes

### Dependencies
- Added `opencv-python>=4.8` to requirements.txt
- Added `numpy>=1.24` to requirements.txt

### File Version Updates
- mjpeg_server.py: v0.1.0 (new)
- handlers.py: v0.5.0 → v0.6.0
- server.py: v0.4.0 → v0.5.0
- main.js: v0.8.0 → v0.9.0
- main.css: v0.6.0 → v0.7.0
- requirements.txt: v1.0.0 → v1.1.0

## 0.6.0 - 2025-12-28
### Camera Detection
- Added automatic camera detection for Windows (DirectShow/WMI) and Linux (v4l2).
- New `backend/camera_detector.py` module (v0.1.0) with cross-platform support.
- API endpoint `GET /api/cameras/detect/` lists available camera devices.
- Support for multiple detection methods: WMI, ffmpeg, OpenCV (Windows), v4l2-ctl, /dev/video scan (Linux).

### Camera Filters
- Added configurable filter patterns to hide unwanted devices (printers, scanners, ISP nodes).
- Default filters for Raspberry Pi internal devices: `bcm2835-isp`, `unicam`, `rp1-cfe`.
- API endpoints for filter management:
  - `GET /api/cameras/filters/` - List patterns
  - `POST /api/cameras/filters/` - Replace all patterns
  - `PUT /api/cameras/filters/` - Add pattern
  - `DELETE /api/cameras/filters/` - Remove pattern
- Filter patterns persisted in `config/motion_frontend.json`.
- UI toggle to show/hide filtered cameras.
- "Manage Filters" dialog for easy pattern management.

### Individual Camera Config Files
- Each camera now has its own JSON config file in `config/cameras/{id}.json`.
- Main config file no longer contains camera configurations.
- Migration support: cameras from old config format automatically moved to individual files.
- Extended CameraConfig with 20+ settings: resolution, framerate, rotation, brightness, contrast, saturation, motion detection, recording options.

### Dynamic Camera Config UI
- Camera config sections dynamically rendered via JavaScript.
- API endpoint `GET /api/config/camera/{id}/sections/` returns UI structure.
- Sections: Device, Video Parameters, Image, Streaming, Motion Detection, Recording.
- Real-time config updates when camera is selected.

### UI Improvements
- New "Add Camera" dialog with detected cameras list.
- Camera selection with visual feedback (icons by source type: USB, CSI, DirectShow).
- One-click camera selection from detected list.
- Quick-hide button to filter unwanted cameras.
- Added `apiPut()` helper function.
- Updated `apiDelete()` to support request body.

### File Version Updates
- config_store.py: v0.5.0 → v0.6.0
- handlers.py: v0.4.0 → v0.5.0
- server.py: v0.3.0 → v0.4.0
- main.js: v0.7.0 → v0.8.0
- main.css: v0.5.0 → v0.6.0
- TECHNICAL_DOCUMENTATION.md: v1.1.0 → v1.2.0

## 0.5.0 - 2025-12-28
### Configuration Persistence
- Added JSON file persistence for all configuration settings (`config/motion_frontend.json`).
- Configuration automatically saves after any modification.
- Configuration file created with defaults if missing (non-blocking startup).
- ConfigStore now supports `save_now()` and `reload()` methods.

### Camera Management
- Added "Add Camera" button functionality in the frontend.
- Modal dialog for adding new cameras with name and device URL fields.
- API endpoint `POST /api/config/camera/add/` for creating cameras.
- API endpoint `DELETE /api/config/camera/{id}/delete/` for removing cameras.
- Automatic camera ID generation (auto-increment).
- Camera list refresh after add/delete operations.

### Backend Improvements
- Updated `config_store.py` (v0.4.0) with full serialization/deserialization.
- Added `add_camera()` and `remove_camera()` methods.
- Extended `save_main_config()` to persist all settings (network, display, auth).
- Added `CameraAddHandler` and `CameraDeleteHandler` in handlers.py (v0.3.0).
- Updated server.py (v0.2.0) with new camera management routes.

### Frontend Improvements  
- Added `apiDelete()` helper function for DELETE requests.
- Added modal dialog system with CSS animations.
- Added `showAddCameraDialog()`, `addCamera()`, `deleteCamera()` functions.
- Added `refreshCameraList()` to update sidebar and dropdowns dynamically.
- Updated main.js (v0.6.0) and main.css (v0.4.0).

## 0.4.0 - 2025-12-28
### Authentification
- Added login page (`templates/login.html`, `static/css/login.css`) with "Remember me" checkbox (30-day session persistence).
- Implemented session-based authentication with secure cookies in `backend/handlers.py`.
- Default credentials: `admin` / `admin`.
- Added logout functionality with session cleanup.

### Interface utilisateur
- Added save button in sidebar that appears only when configuration has been modified (dirty tracking).
- Added "Display Settings" section with preview count selector (1/2/4/8/16/32) and quality setting.
- Added language selector in General Settings (fr/en/de/es/it).
- Increased sidebar width (320-420px) for better readability.
- Reduced font sizes throughout sidebar menu for better density.
- Added admin/user account management fields in General Settings.

### Preview Grid
- Implemented dynamic preview grid supporting 1, 2, 4, 8, 16, and 32 simultaneous camera views.
- Grid layout adapts automatically based on preview count setting.
- Added dummy placeholder images for development (via placehold.co).
- Fixed preview area to never exceed viewport height (`calc(100vh - 180px)`).

### Documentation
- Created comprehensive technical documentation (`docs/TECHNICAL_DOCUMENTATION.md`).

## 0.3.0 - 2025-12-28
- Added the Tornado application entry point (`backend/server.py`) that wires templates, static assets, and config APIs, exposing `/health`, `/version`, and camera endpoints for local development.
- Introduced [scripts/run_motion_frontend.ps1](scripts/run_motion_frontend.ps1) to launch the backend, probe readiness, and open the Motion Frontend UI automatically on Windows workstations.
- Fixed the `config_item` macro in [templates/main.html](templates/main.html) so it no longer uses unsupported Jinja `return` statements, allowing the frontend to render without template errors.
- Added a default `_()` translation helper inside the Jinja environment so templates render cleanly even before gettext catalogs are wired up.
- Ensured all templates receive `static_path`/`version` defaults from [backend/handlers.py](backend/handlers.py) so JSON serialization of the motion context no longer fails when optional values are omitted.
- Reworked [templates/main.html](templates/main.html), [static/css/main.css](static/css/main.css), and [static/js/main.js](static/js/main.js) to place all configuration menus inside a retractable left sidebar while keeping the live preview anchored to the right, complete with scrim overlay, Escape-to-close, and responsive behavior.
- Added [static/manifest.json](static/manifest.json) so the `<link rel="manifest">` reference resolves without 404 errors.

## 0.2.1 - 2025-12-28
- Windows installer now opens the configured frontend URL automatically after install/update; use `-LaunchUrl` to customize or `-NoLaunch` to skip.

## 0.2.0 - 2025-12-28
- Rebranded the full UI stack to Motion Frontend (templates, manifests, JS globals, docs, assets).
- Added dedicated localization bundles (`motion_frontend.<lang>.json`) and refreshed the logo for the new identity.
- Vendor bundles (jQuery, timepicker, mousewheel, css-browser-selector, gettext) downloaded into `static/vendor/` for offline deployments.
- Introduced [scripts/install_motion_frontend.ps1](scripts/install_motion_frontend.ps1) to install/update/uninstall builds on Windows, including optional ZIP packaging.

## 0.1.0 - 2025-12-28
- Initial repository bootstrap: documentation scaffold, planned structure, groundwork for templates and assets.
