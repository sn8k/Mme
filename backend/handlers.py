# File Version: 0.30.2
from __future__ import annotations

import aiohttp
import base64
import hashlib
import json
import logging
import platform
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import tornado.web
import tornado.escape
import tornado.iostream

from .config_store import ConfigStore, resolve_video_device, resolve_audio_device
from .jinja import render
from . import camera_detector
from . import audio_detector
from . import mjpeg_server
from . import meeting_service
from . import updater
from . import rtsp_server
from . import system_info
from .user_manager import get_user_manager, UserManager, UserRole, User

logger = logging.getLogger(__name__)

_PLACEHOLDER_FRAME = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8\n/w8AAuMBg6RYw1cAAAAASUVORK5CYII="
)

# Session store with file persistence for "remember me"
_SESSIONS_FILE = Path("config/sessions.json")
_SESSIONS: Dict[str, str] = {}


def _load_sessions() -> None:
    """Load sessions from file for persistence across restarts."""
    global _SESSIONS
    try:
        if _SESSIONS_FILE.exists():
            with _SESSIONS_FILE.open("r", encoding="utf-8") as f:
                _SESSIONS = json.load(f)
    except Exception:
        _SESSIONS = {}


def _save_sessions() -> None:
    """Save sessions to file for persistence."""
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _SESSIONS_FILE.open("w", encoding="utf-8") as f:
            json.dump(_SESSIONS, f)
    except Exception:
        pass


# Load sessions on module import
_load_sessions()


class BaseHandler(tornado.web.RequestHandler):
    @property
    def config_store(self) -> ConfigStore:
        return self.application.settings["config_store"]  # type: ignore[index]
    
    @property
    def user_manager(self) -> UserManager:
        return get_user_manager()

    @property
    def jinja_env(self):
        return self.application.settings["jinja_env"]

    def get_current_user(self) -> Optional[str]:
        session_id = self.get_secure_cookie("session_id")
        if session_id:
            session_id_str = session_id.decode("utf-8")
            return _SESSIONS.get(session_id_str)
        return None
    
    def get_current_user_info(self) -> Optional[User]:
        """Get full User object for current authenticated user."""
        username = self.get_current_user()
        if username:
            return self.user_manager.get_user(username)
        return None
    
    def is_admin(self) -> bool:
        """Check if current user is an admin."""
        user = self.get_current_user_info()
        return user is not None and user.role == UserRole.ADMIN

    def write_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(payload))


class TemplateHandler(BaseHandler):
    template_name: str = "main.html"

    def render_template(self, **context: Any) -> None:
        base_context = {
            "static_path": self.application.settings.get("static_url_prefix", "/static").rstrip("/"),
            "version": self.application.settings.get("frontend_version", "dev"),
        }
        base_context.update(context)
        html = render(self.jinja_env, self.template_name, base_context)
        self.write(html)


class LoginHandler(TemplateHandler):
    template_name = "login.html"

    async def get(self) -> None:
        if self.get_current_user():
            self.redirect("/")
            return
        self.render_template(error=None, lingvo="fr")

    async def post(self) -> None:
        username = self.get_body_argument("username", "")
        password = self.get_body_argument("password", "")
        remember_me = self.get_body_argument("remember_me", "off") == "on"
        
        user = self.user_manager.authenticate(username, password)
        if user:
            # Only admin users can access the UI
            from .user_manager import UserRole
            if user.role != UserRole.ADMIN:
                self.render_template(error="Accès réservé aux administrateurs", lingvo="fr")
                return
            
            session_id = secrets.token_hex(32)
            _SESSIONS[session_id] = username
            # Persist sessions to file for "remember me" to survive restarts
            _save_sessions()
            # 30 days if remember me, else session cookie
            expires_days = 30 if remember_me else None
            self.set_secure_cookie("session_id", session_id, httponly=True, expires_days=expires_days)
            
            # Check if user must change password
            if user.must_change_password:
                self.redirect("/?change_password=1")
            else:
                self.redirect("/")
        else:
            self.render_template(error="Identifiant ou mot de passe incorrect", lingvo="fr")


class LogoutHandler(BaseHandler):
    async def get(self) -> None:
        session_id = self.get_secure_cookie("session_id")
        if session_id:
            session_id_str = session_id.decode("utf-8")
            _SESSIONS.pop(session_id_str, None)
            _save_sessions()  # Persist session removal
        self.clear_cookie("session_id")
        self.redirect("/login")


class MainHandler(TemplateHandler):
    def get_login_url(self) -> str:
        return "/login"

    @tornado.web.authenticated
    async def get(self) -> None:
        camera_id = self.get_query_argument("camera", default=None)
        audio_id = self.get_query_argument("audio", default=None)
        main_sections = self.config_store.get_main_config()
        
        # Get camera config sections if a camera is selected
        camera_config_sections = []
        if camera_id:
            camera_config_sections = self.config_store.get_camera_config_sections(camera_id)
        
        # Get audio config sections if an audio device is selected
        audio_config_sections = []
        if audio_id:
            audio_config_sections = self.config_store.get_audio_config_sections(audio_id)
        
        template_context = {
            "lingvo": "fr",
            "version": self.application.settings.get("frontend_version", "dev"),
            "hostname": self.config_store.get_hostname(),
            "cameras": self.config_store.get_cameras(),
            "camera_id": camera_id,
            "audio_devices": self.config_store.get_audio_devices(),
            "audio_id": audio_id,
            "general": main_sections.get("general", []),
            "display_settings": main_sections.get("display_settings", []),
            "network_manager": main_sections.get("network_manager", []),
            "meeting": main_sections.get("meeting", []),
            "backup": main_sections.get("backup", []),
            "main_sections": [],
            # Dynamic camera config sections
            "camera_config_sections": camera_config_sections,
            # Dynamic audio config sections
            "audio_config_sections": audio_config_sections,
            "frame": False,
            "admin_username": "admin",
            "has_local_cam_support": True,
            "has_net_cam_support": True,
            "mask_width": 16,
        }
        self.render_template(**template_context)


class VersionHandler(BaseHandler):
    async def get(self) -> None:
        from . import updater
        
        # Get current version dynamically from CHANGELOG (not cached)
        current_version = updater.get_current_version()
        
        payload = self.config_store.get_version_payload(
            frontend_version=current_version,
            commit=self.application.settings.get("git_commit", "dev"),
        )
        self.write_json(payload)


class ConfigMainHandler(BaseHandler):
    async def get(self) -> None:
        self.write_json(self.config_store.get_main_config())

    async def post(self) -> None:
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        result = self.config_store.save_main_config(payload)
        self.write_json(result)


class ConfigListHandler(BaseHandler):
    async def get(self) -> None:
        self.write_json({"cameras": self.config_store.get_cameras()})


class ConfigCameraHandler(BaseHandler):
    async def get(self, camera_id: str) -> None:
        camera = self.config_store.get_camera_config(camera_id)
        if not camera:
            self.write_json({"error": "Camera not found"}, status=404)
            return
        self.write_json(camera)

    async def post(self, camera_id: str) -> None:
        from . import mjpeg_server
        from . import rtsp_server
        
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        
        # Check if stream is running before saving
        server = mjpeg_server.get_mjpeg_server()
        status = server.get_camera_status(camera_id)
        was_streaming = status.get("is_running", False)
        
        # Check current RTSP state before saving
        old_camera = self.config_store.get_camera(camera_id)
        old_rtsp_enabled = old_camera.rtsp_enabled if old_camera else False
        new_rtsp_enabled = payload.get("rtspEnabled", old_rtsp_enabled)
        new_rtsp_audio = payload.get("rtspAudioDevice", "")
        
        try:
            result = self.config_store.save_camera_config(camera_id, payload)
        except KeyError:
            self.write_json({"error": "Camera not found"}, status=404)
            return
        
        # If stream was running, restart it to apply new settings
        if was_streaming:
            # Stop the stream
            server.stop_camera(camera_id)
            # Remove camera from server to force reconfiguration
            server.remove_camera(camera_id)
            
            # Wait a moment for HTTP server port to be released
            import asyncio
            await asyncio.sleep(0.5)
            
            # Get updated camera config
            camera = self.config_store.get_camera(camera_id)
            if camera:
                # Parse resolutions
                try:
                    width, height = map(int, camera.resolution.split("x"))
                except:
                    width, height = 640, 480
                try:
                    stream_width, stream_height = map(int, camera.stream_resolution.split("x"))
                except:
                    stream_width, stream_height = 0, 0
                
                # Create auth verification callback using UserManager
                def verify_stream_auth(username: str, password: str) -> bool:
                    return self.user_manager.verify_credentials(username, password)
                
                # Re-add camera with new settings - resolve stable device path
                device_path = camera.device_settings.get("device", "0")
                stable_path = camera.device_settings.get("stable_device_path", "")
                resolved_device = resolve_video_device(device_path, stable_path)
                logger.debug("MJPEG restart: Device resolution for camera %s: %s -> %s",
                            camera_id, device_path, resolved_device)
                
                server.add_camera(
                    camera_id=camera_id,
                    device_path=resolved_device,
                    name=camera.name,
                    width=width,
                    height=height,
                    stream_width=stream_width,
                    stream_height=stream_height,
                    fps=camera.framerate,
                    quality=camera.jpeg_quality,
                    mjpeg_port=camera.mjpeg_port,
                    overlay_left_text=camera.overlay_left_text,
                    overlay_left_custom=camera.overlay_left_custom,
                    overlay_right_text=camera.overlay_right_text,
                    overlay_right_custom=camera.overlay_right_custom,
                    overlay_text_scale=camera.overlay_text_scale,
                    stream_auth_enabled=camera.stream_auth_enabled,
                    stream_auth_verify=verify_stream_auth if camera.stream_auth_enabled else None,
                )
                # Restart stream
                server.start_camera(camera_id)
                result["stream_restarted"] = True
        
        # Handle RTSP enable/disable
        rtsp = rtsp_server.get_rtsp_server()
        logger.info("RTSP config change: old_enabled=%s, new_enabled=%s, audio=%s", 
                    old_rtsp_enabled, new_rtsp_enabled, new_rtsp_audio)
        
        if new_rtsp_enabled and not old_rtsp_enabled:
            # Enable RTSP - start the stream
            logger.info("RTSP: Starting stream for camera %s", camera_id)
            result["rtsp_action"] = "starting"
            try:
                camera = self.config_store.get_camera(camera_id)
                logger.debug("RTSP: Camera config: %s", camera)
                logger.debug("RTSP: FFmpeg available: %s", rtsp.is_ffmpeg_available())
                
                if camera and rtsp.is_ffmpeg_available():
                    # On Linux, check if Motion is running and using the camera
                    # Motion holds exclusive access to cameras, so RTSP/FFmpeg will fail
                    if platform.system().lower() == "linux":
                        motion_port = camera.motion_stream_port or 8081
                        if system_info.is_motion_running(motion_port):
                            logger.warning("RTSP: Motion daemon detected on port %d - camera may be busy", motion_port)
                            result["motion_warning"] = True
                            result["motion_message"] = (
                                "Motion daemon is running and may be using this camera. "
                                "RTSP stream may fail. Consider stopping Motion first: "
                                "sudo systemctl stop motion"
                            )
                    
                    # Stop MJPEG stream first to release camera (Windows can only have one process access camera)
                    mjpeg = mjpeg_server.get_mjpeg_server()
                    if mjpeg:
                        logger.info("RTSP: Stopping MJPEG stream to release camera")
                        mjpeg.stop_camera(camera_id)
                        result["mjpeg_stopped"] = True
                    
                    rtsp_port = rtsp.get_rtsp_port_for_camera(camera_id)
                    logger.info("RTSP: Using port %d for camera %s", rtsp_port, camera_id)
                    
                    # Resolve device path using stable path if available
                    device_path = camera.device_settings.get("device", "0")
                    stable_path = camera.device_settings.get("stable_device_path", "")
                    resolved_device = resolve_video_device(device_path, stable_path)
                    logger.info("RTSP: Device resolution: %s (stable: %s) -> %s", 
                               device_path, stable_path, resolved_device)
                    
                    # Build stream config
                    config = rtsp_server.RTSPStreamConfig(
                        camera_id=camera_id,
                        camera_device=resolved_device,
                        camera_name=camera.name,
                        resolution=camera.resolution,
                        framerate=camera.framerate,
                        video_bitrate=2000,
                        rtsp_port=rtsp_port,
                        rtsp_path=f"/cam{camera_id}",
                    )
                    logger.debug("RTSP: Stream config: device=%s, name=%s, resolution=%s, fps=%d",
                                config.camera_device, config.camera_name, config.resolution, config.framerate)
                    
                    # Add audio if selected
                    if new_rtsp_audio:
                        logger.info("RTSP: Adding audio device: %s", new_rtsp_audio)
                        audio = self.config_store.get_audio_device(new_rtsp_audio)
                        if audio and audio.enabled:
                            # Resolve audio device using stable ID if available
                            audio_device_id = audio.device_id
                            stable_audio_id = audio.device_settings.get("stable_id", "")
                            resolved_audio = resolve_audio_device(audio_device_id, stable_audio_id)
                            logger.info("RTSP: Audio device resolution: %s (stable: %s) -> %s", 
                                       audio_device_id, stable_audio_id, resolved_audio)
                            
                            config.audio_device_id = resolved_audio
                            config.audio_device_name = audio.name
                            config.audio_sample_rate = audio.sample_rate
                            config.audio_channels = audio.channels
                            config.audio_bitrate = audio.bitrate
                            config.audio_codec = audio.codec
                            logger.debug("RTSP: Audio config: id=%s, rate=%d, channels=%d",
                                        resolved_audio, audio.sample_rate, audio.channels)
                    
                    logger.info("RTSP: Calling start_stream()...")
                    status = await rtsp.start_stream(config)
                    logger.info("RTSP: start_stream() returned: running=%s, url=%s, error=%s",
                               status.is_running, status.rtsp_url, status.error)
                    result["rtsp_started"] = status.is_running
                    result["rtsp_url"] = status.rtsp_url
                    result["rtsp_error"] = status.error
                else:
                    error_msg = "FFmpeg not available" if not rtsp.is_ffmpeg_available() else "Camera not found"
                    logger.error("RTSP: Cannot start - %s", error_msg)
                    result["rtsp_error"] = error_msg
            except Exception as e:
                logger.exception("RTSP: Exception while starting stream")
                result["rtsp_error"] = str(e)
                
        elif not new_rtsp_enabled and old_rtsp_enabled:
            # Disable RTSP - stop the stream
            logger.info("RTSP: Stopping stream for camera %s", camera_id)
            result["rtsp_action"] = "stopping"
            try:
                await rtsp.stop_stream(camera_id)
                result["rtsp_stopped"] = True
                logger.info("RTSP: Stream stopped successfully")
                
                # Restart MJPEG stream now that camera is free
                mjpeg = mjpeg_server.get_mjpeg_server()
                camera = self.config_store.get_camera(camera_id)
                if mjpeg and camera and camera.enabled:
                    logger.info("RTSP: Restarting MJPEG stream")
                    mjpeg.start_camera(camera_id)
                    result["mjpeg_restarted"] = True
            except Exception as e:
                result["rtsp_error"] = str(e)
        
        self.write_json(result)


class CameraAddHandler(BaseHandler):
    """Handle camera addition requests."""
    
    async def post(self) -> None:
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        name = payload.get("name", "")
        device_url = payload.get("device_url", "")
        
        result = self.config_store.add_camera(name=name, device_url=device_url)
        self.write_json(result, status=201)


class CameraDeleteHandler(BaseHandler):
    """Handle camera deletion requests."""
    
    async def delete(self, camera_id: str) -> None:
        try:
            result = self.config_store.remove_camera(camera_id)
            self.write_json(result)
        except KeyError:
            self.write_json({"error": "Camera not found"}, status=404)


class CameraConfigSectionsHandler(BaseHandler):
    """Return camera configuration sections for dynamic UI rendering."""
    
    async def get(self, camera_id: str) -> None:
        sections = self.config_store.get_camera_config_sections(camera_id)
        if not sections:
            self.write_json({"error": "Camera not found"}, status=404)
            return
        self.write_json({"sections": sections})


class LoggingConfigHandler(BaseHandler):
    async def post(self) -> None:
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        level = payload.get("level", "INFO")
        self.config_store.set_logging_level(level)
        self.write_json({"status": "ok", "level": self.config_store.get_logging_level()})


class HealthHandler(BaseHandler):
    async def get(self) -> None:
        self.write_json({"status": "ok"})


class CameraDetectHandler(BaseHandler):
    """Detect available cameras on the system."""
    
    async def get(self) -> None:
        """Get list of detected cameras.
        
        Query params:
            include_filtered: if "true", include cameras matching filter patterns
        """
        include_filtered = self.get_argument("include_filtered", "false").lower() == "true"
        
        # Get filter patterns from config
        filter_patterns = self.config_store.get_camera_filter_patterns()
        
        # Update detector with current patterns
        detector = camera_detector.get_detector()
        detector.filter_patterns = filter_patterns
        
        # Detect cameras
        cameras = detector.detect_cameras(include_filtered=include_filtered)
        
        self.write_json({
            "cameras": [c.to_dict() for c in cameras],
            "filter_patterns": filter_patterns,
            "platform": detector._system,
        })


class CameraCapabilitiesHandler(BaseHandler):
    """Detect camera capabilities (supported resolutions, FPS, etc.)."""
    
    async def get(self, device_path: str) -> None:
        """Get capabilities of a specific camera device.
        
        Args:
            device_path: Device path or index (URL encoded).
        """
        from . import mjpeg_server
        
        # URL decode the device path
        import urllib.parse
        device_path = urllib.parse.unquote(device_path)
        
        server = mjpeg_server.get_mjpeg_server()
        if not mjpeg_server.is_opencv_available():
            self.write_json({
                "error": "OpenCV not available",
                "supported_resolutions": [],
                "current_resolution": None,
                "max_fps": 30,
            })
            return
        
        capabilities = server.detect_camera_capabilities(device_path)
        self.write_json(capabilities)


class CameraControlsHandler(BaseHandler):
    """Detect and manage camera controls (brightness, contrast, etc.)."""
    
    async def get(self, device_path: str) -> None:
        """Get available controls for a camera device.
        
        Args:
            device_path: Device path or index (URL encoded).
            
        Returns:
            JSON with list of available controls.
        """
        from . import camera_detector
        import urllib.parse
        
        device_path = urllib.parse.unquote(device_path)
        controls = camera_detector.detect_camera_controls(device_path)
        
        # detect_camera_controls already returns dictionaries
        self.write_json({
            "device": device_path,
            "controls": controls,
            "count": len(controls),
        })
    
    async def post(self, device_path: str) -> None:
        """Set a camera control value.
        
        Args:
            device_path: Device path or index (URL encoded).
            
        Request body:
            {
                "control_id": "brightness",
                "value": 50
            }
        """
        from . import camera_detector
        import urllib.parse
        
        device_path = urllib.parse.unquote(device_path)
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        
        control_id = payload.get("control_id")
        value = payload.get("value")
        
        if not control_id:
            self.write_json({"error": "control_id is required"}, status=400)
            return
        
        if value is None:
            self.write_json({"error": "value is required"}, status=400)
            return
        
        try:
            value = int(value)
        except (TypeError, ValueError):
            self.write_json({"error": "value must be an integer"}, status=400)
            return
        
        success = camera_detector.set_camera_control(device_path, control_id, value)
        
        if success:
            self.write_json({
                "status": "ok",
                "device": device_path,
                "control_id": control_id,
                "value": value,
            })
        else:
            self.write_json({
                "error": f"Failed to set {control_id}",
                "device": device_path,
            }, status=500)


class CameraFilterPatternsHandler(BaseHandler):
    """Manage camera filter patterns."""
    
    async def get(self) -> None:
        """Get current filter patterns."""
        patterns = self.config_store.get_camera_filter_patterns()
        self.write_json({"patterns": patterns})
    
    async def post(self) -> None:
        """Set filter patterns."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        patterns = payload.get("patterns", [])
        
        if not isinstance(patterns, list):
            self.write_json({"error": "patterns must be a list"}, status=400)
            return
        
        self.config_store.set_camera_filter_patterns(patterns)
        self.write_json({"status": "ok", "patterns": patterns})
    
    async def put(self) -> None:
        """Add a filter pattern."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        pattern = payload.get("pattern", "")
        
        if not pattern:
            self.write_json({"error": "pattern is required"}, status=400)
            return
        
        self.config_store.add_camera_filter_pattern(pattern)
        self.write_json({"status": "ok", "patterns": self.config_store.get_camera_filter_patterns()})
    
    async def delete(self) -> None:
        """Remove a filter pattern."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        pattern = payload.get("pattern", "")
        
        if not pattern:
            self.write_json({"error": "pattern is required"}, status=400)
            return
        
        self.config_store.remove_camera_filter_pattern(pattern)
        self.write_json({"status": "ok", "patterns": self.config_store.get_camera_filter_patterns()})


class FrameHandler(BaseHandler):
    """Returns a single JPEG frame from a camera."""
    
    async def get(self, camera_id: str) -> None:
        # Check if RTSP is active for this camera (MJPEG unavailable when RTSP is using camera)
        rtsp = rtsp_server.get_rtsp_server()
        rtsp_status = rtsp.get_stream_status(camera_id)
        if rtsp_status and rtsp_status.is_running:
            # Return a placeholder indicating RTSP is active
            self.set_header("Content-Type", "image/svg+xml")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
            svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
                <rect fill="#1a1a2e" width="100%" height="100%"/>
                <text x="50%" y="45%" text-anchor="middle" fill="#4ade80" font-family="Arial" font-size="24" font-weight="bold">RTSP Stream Active</text>
                <text x="50%" y="55%" text-anchor="middle" fill="#9ca3af" font-family="Arial" font-size="14">Preview unavailable - Use RTSP client</text>
                <text x="50%" y="65%" text-anchor="middle" fill="#60a5fa" font-family="monospace" font-size="12">rtsp://HOST:''' + str(rtsp_status.rtsp_url.split(':')[-1].split('/')[0] if rtsp_status.rtsp_url else '8554') + '''/cam''' + camera_id + '''</text>
            </svg>'''
            self.write(svg)
            return
        
        # Check stream source - Motion or internal
        camera = self.config_store.get_camera(camera_id)
        motion_running = False
        if platform.system().lower() == "linux":
            motion_running = system_info.is_motion_running()
        
        stream_source = camera.stream_source if camera else "auto"
        use_motion = stream_source == "motion" or (stream_source == "auto" and motion_running)
        
        if use_motion and camera:
            # Fetch frame from Motion
            motion_port = camera.motion_stream_port or 8081
            frame = await self._fetch_motion_frame(motion_port, camera_id)
            if frame:
                logger.debug("Frame from Motion for camera %s (port %d)", camera_id, motion_port)
                self.set_header("Content-Type", "image/jpeg")
                self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.write(frame)
                return
            else:
                logger.debug("Failed to fetch frame from Motion for camera %s, falling back", camera_id)
        
        # Use internal MJPEG server
        server = mjpeg_server.get_mjpeg_server()
        frame = server.get_frame(camera_id)
        
        if frame:
            self.set_header("Content-Type", "image/jpeg")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.write(frame)
        else:
            self.set_header("Content-Type", "image/png")
            self.write(_PLACEHOLDER_FRAME)
    
    async def _fetch_motion_frame(self, port: int, camera_id: str) -> bytes | None:
        """Fetch a single JPEG frame from Motion's stream."""
        # Motion exposes streams at different URLs depending on configuration
        # Try the standard stream URL first, then the picture URL
        urls_to_try = [
            f"http://127.0.0.1:{port}/{camera_id}/current/",  # Motion 4.x single frame
            f"http://127.0.0.1:{port}/current/",  # Motion single camera
            f"http://127.0.0.1:{port}/{camera_id}/stream/",  # Motion stream
            f"http://127.0.0.1:{port}/",  # Direct stream (for older Motion)
        ]
        
        for url in urls_to_try:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            content_type = resp.headers.get("Content-Type", "")
                            if "image/jpeg" in content_type:
                                data = await resp.read()
                                logger.debug("Got frame from Motion URL: %s (%d bytes)", url, len(data))
                                return data
                            elif "multipart" in content_type:
                                # MJPEG stream - read first frame
                                data = await resp.content.read(100000)  # Read up to 100KB
                                # Find JPEG boundaries
                                start = data.find(b'\xff\xd8')
                                end = data.find(b'\xff\xd9', start)
                                if start >= 0 and end > start:
                                    frame = data[start:end+2]
                                    logger.debug("Extracted frame from Motion MJPEG: %s (%d bytes)", url, len(frame))
                                    return frame
            except Exception as e:
                logger.debug("Failed to fetch from %s: %s", url, e)
                continue
        
        return None


class MJPEGStreamHandler(BaseHandler):
    """MJPEG stream handler - provides continuous video stream."""
    
    async def get(self, camera_id: str) -> None:
        """Stream MJPEG frames continuously."""
        # Check if RTSP is enabled in camera config (blocks MJPEG even during RTSP startup)
        camera_config = self.config_store.get_camera(camera_id)
        rtsp_enabled_in_config = camera_config and camera_config.rtsp_enabled
        
        # Also check if RTSP stream is actually running
        rtsp = rtsp_server.get_rtsp_server()
        rtsp_status = rtsp.get_stream_status(camera_id)
        rtsp_is_running = rtsp_status and rtsp_status.is_running
        
        # Block MJPEG if RTSP is enabled in config OR if RTSP stream is running
        if rtsp_enabled_in_config or rtsp_is_running:
            logger.debug("MJPEG stream blocked for camera %s: rtsp_enabled=%s, rtsp_running=%s",
                        camera_id, rtsp_enabled_in_config, rtsp_is_running)
            # Return single frame indicating RTSP is active (not a stream)
            self.set_header("Content-Type", "image/svg+xml")
            self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
            port = rtsp_status.rtsp_url.split(':')[-1].split('/')[0] if rtsp_status and rtsp_status.rtsp_url else '8554'
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
                <rect fill="#1a1a2e" width="100%" height="100%"/>
                <text x="50%" y="45%" text-anchor="middle" fill="#4ade80" font-family="Arial" font-size="24" font-weight="bold">RTSP Stream Active</text>
                <text x="50%" y="55%" text-anchor="middle" fill="#9ca3af" font-family="Arial" font-size="14">Preview unavailable - Use RTSP client</text>
                <text x="50%" y="65%" text-anchor="middle" fill="#60a5fa" font-family="monospace" font-size="12">rtsp://HOST:{port}/cam{camera_id}</text>
            </svg>'''
            self.write(svg)
            return
        
        # Check stream source - Motion or internal
        motion_running = False
        if platform.system().lower() == "linux":
            motion_running = system_info.is_motion_running()
        
        stream_source = camera_config.stream_source if camera_config else "auto"
        use_motion = stream_source == "motion" or (stream_source == "auto" and motion_running)
        
        if use_motion and camera_config:
            # Proxy Motion stream to client
            motion_port = camera_config.motion_stream_port or 8081
            logger.info("MJPEG stream proxying to Motion for camera %s (port %d)", camera_id, motion_port)
            await self._proxy_motion_stream(motion_port, camera_id)
            return
        
        # Use internal MJPEG server
        server = mjpeg_server.get_mjpeg_server()
        
        # Check if camera exists and is running
        status = server.get_camera_status(camera_id)
        if not status.get("exists"):
            self.set_status(404)
            self.write_json({"error": "Camera not found"})
            return
        
        # Set headers for MJPEG stream
        self.set_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Connection", "close")
        self.set_header("Pragma", "no-cache")
        
        try:
            async for frame in server.frame_generator(camera_id):
                try:
                    self.write(frame)
                    await self.flush()
                except tornado.iostream.StreamClosedError:
                    # Client disconnected
                    break
        except Exception as e:
            # Log but don't raise - client likely disconnected
            pass
    
    async def _proxy_motion_stream(self, port: int, camera_id: str) -> None:
        """Proxy Motion's MJPEG stream to the client."""
        # Try different Motion stream URLs
        urls_to_try = [
            f"http://127.0.0.1:{port}/{camera_id}/stream",  # Motion 4.x per-camera
            f"http://127.0.0.1:{port}/stream",  # Motion single stream
            f"http://127.0.0.1:{port}/",  # Direct stream (older Motion)
        ]
        
        for url in urls_to_try:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=None, connect=5)) as resp:
                        if resp.status != 200:
                            continue
                        
                        content_type = resp.headers.get("Content-Type", "")
                        if "multipart" not in content_type and "image" not in content_type:
                            continue
                        
                        logger.info("Motion stream proxy connected to %s", url)
                        
                        # Set headers for MJPEG stream
                        self.set_header("Content-Type", content_type)
                        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
                        self.set_header("Connection", "close")
                        self.set_header("Pragma", "no-cache")
                        
                        # Stream data from Motion to client
                        try:
                            async for chunk in resp.content.iter_any():
                                try:
                                    self.write(chunk)
                                    await self.flush()
                                except tornado.iostream.StreamClosedError:
                                    # Client disconnected
                                    logger.debug("Client disconnected from Motion proxy")
                                    return
                        except Exception as e:
                            logger.debug("Motion stream ended: %s", e)
                        return
                        
            except asyncio.TimeoutError:
                logger.debug("Timeout connecting to Motion at %s", url)
                continue
            except Exception as e:
                logger.debug("Failed to connect to Motion at %s: %s", url, e)
                continue
        
        # No Motion stream found - return error
        logger.warning("Could not connect to Motion stream on port %d", port)
        self.set_status(503)
        self.write_json({"error": "Motion stream unavailable"})


class MJPEGControlHandler(BaseHandler):
    """Control MJPEG streams - start/stop cameras."""
    
    async def get(self) -> None:
        """Get status of all MJPEG streams."""
        server = mjpeg_server.get_mjpeg_server()
        status = server.get_all_status()
        
        # Check if Motion is running (Linux only)
        motion_running = False
        if platform.system().lower() == "linux":
            motion_running = system_info.is_motion_running()
        
        # Add Motion stream info for cameras and fill in config-based stats
        for camera_id, cam_status in status.items():
            camera = self.config_store.get_camera(camera_id)
            if camera:
                motion_port = camera.motion_stream_port or 8081
                stream_source = camera.stream_source or "auto"
                
                # Determine effective source
                use_motion = stream_source == "motion" or (stream_source == "auto" and motion_running)
                
                if use_motion:
                    cam_status["stream_source"] = "motion"
                    cam_status["motion_stream_port"] = motion_port
                    cam_status["motion_auto_detected"] = (stream_source == "auto")
                    # For Motion source, provide config-based stats (Motion doesn't expose real stats)
                    # Mark as "running" if Motion is running, so UI shows stream is active
                    cam_status["is_running"] = motion_running
                    cam_status["exists"] = True
                    # Parse resolution from config
                    try:
                        w, h = map(int, camera.stream_resolution.split("x"))
                        cam_status["width"] = w
                        cam_status["height"] = h
                    except:
                        cam_status["width"] = 640
                        cam_status["height"] = 480
                    cam_status["fps"] = camera.stream_framerate
                    # Can't measure real FPS/bandwidth for Motion proxy, use configured values
                    cam_status["real_fps"] = camera.stream_framerate
                    cam_status["bandwidth_kbps"] = 0  # Unknown for Motion
                else:
                    cam_status["stream_source"] = "internal"
        
        self.write_json({
            "opencv_available": mjpeg_server.is_opencv_available(),
            "motion_running": motion_running,
            "cameras": status
        })
    
    async def post(self) -> None:
        """Start or stop a camera stream."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        action = payload.get("action", "")
        camera_id = payload.get("camera_id", "")
        
        server = mjpeg_server.get_mjpeg_server()
        
        if action == "start":
            # Get camera config
            camera = self.config_store.get_camera(camera_id)
            if not camera:
                self.write_json({"error": "Camera not found"}, status=404)
                return
            
            # Check if RTSP is enabled for this camera - don't start MJPEG if so
            if camera.rtsp_enabled:
                logger.info("MJPEG start skipped for camera %s: RTSP is active", camera_id)
                self.write_json({
                    "status": "skipped",
                    "reason": "RTSP is active for this camera",
                    "camera": {
                        "camera_id": camera_id,
                        "is_running": False,
                        "rtsp_enabled": True,
                        "name": camera.name,
                    }
                })
                return
            
            # Determine stream source: auto, internal, or motion
            # - auto: Use Motion if running on Linux, else internal
            # - internal: Force our MJPEG server
            # - motion: Force Motion's stream
            use_motion = False
            motion_port = camera.motion_stream_port or 8081
            stream_source = camera.stream_source or "auto"
            
            if stream_source == "internal":
                # User explicitly wants internal MJPEG server
                logger.debug("MJPEG: Camera %s using internal source (explicit)", camera_id)
                use_motion = False
            elif stream_source == "motion":
                # User explicitly wants Motion
                logger.debug("MJPEG: Camera %s using Motion source (explicit)", camera_id)
                use_motion = True
            elif stream_source == "auto" and platform.system().lower() == "linux":
                # Auto-detect: use Motion if running on Linux
                if system_info.is_motion_running(motion_port):
                    logger.info("MJPEG: Camera %s auto-detected Motion on port %d", camera_id, motion_port)
                    use_motion = True
                else:
                    logger.debug("MJPEG: Camera %s using internal source (Motion not running)", camera_id)
                    use_motion = False
            
            if use_motion:
                # For Motion source, we don't start our internal server
                # Just return success with Motion stream info
                import socket
                try:
                    server_ip = socket.gethostbyname(socket.gethostname())
                except:
                    server_ip = "localhost"
                
                # Build correct Motion stream URL
                # Motion 4.x exposes streams at /stream or /{camera_id}/stream
                # We'll use /stream which is the most common configuration
                motion_stream_url = f"http://{server_ip}:{motion_port}/stream"
                
                self.write_json({
                    "status": "ok",
                    "camera": {
                        "camera_id": camera_id,
                        "is_running": True,
                        "stream_source": "motion",
                        "motion_stream_port": motion_port,
                        "motion_stream_url": motion_stream_url,
                        "name": camera.name,
                        "auto_detected": camera.stream_source != "motion",
                    }
                })
                return
            
            # Get device path and resolve stable path if available
            device_path = camera.device_settings.get("device", "0")
            stable_path = camera.device_settings.get("stable_device_path", "")
            resolved_device = resolve_video_device(device_path, stable_path)
            logger.debug("MJPEG: Device resolution for camera %s: %s (stable: %s) -> %s",
                        camera_id, device_path, stable_path, resolved_device)
            
            # Parse capture resolution (input)
            try:
                width, height = map(int, camera.resolution.split("x"))
            except:
                width, height = 640, 480
            
            # Parse stream resolution (output)
            try:
                stream_width, stream_height = map(int, camera.stream_resolution.split("x"))
            except:
                stream_width, stream_height = 0, 0  # 0 = same as capture
            
            # Create auth verification callback using UserManager
            def verify_stream_auth(username: str, password: str) -> bool:
                return self.user_manager.verify_credentials(username, password)
            
            # Add camera to MJPEG server if not already added
            if not server.get_camera_status(camera_id).get("exists"):
                server.add_camera(
                    camera_id=camera_id,
                    device_path=resolved_device,
                    name=camera.name,
                    width=width,
                    height=height,
                    stream_width=stream_width,
                    stream_height=stream_height,
                    fps=camera.framerate,
                    quality=camera.jpeg_quality,
                    mjpeg_port=camera.mjpeg_port,
                    overlay_left_text=camera.overlay_left_text,
                    overlay_left_custom=camera.overlay_left_custom,
                    overlay_right_text=camera.overlay_right_text,
                    overlay_right_custom=camera.overlay_right_custom,
                    overlay_text_scale=camera.overlay_text_scale,
                    stream_auth_enabled=camera.stream_auth_enabled,
                    stream_auth_verify=verify_stream_auth if camera.stream_auth_enabled else None,
                )
            else:
                # Update overlay settings if camera already exists
                server.update_camera(
                    camera_id=camera_id,
                    overlay_left_text=camera.overlay_left_text,
                    overlay_left_custom=camera.overlay_left_custom,
                    overlay_right_text=camera.overlay_right_text,
                    overlay_right_custom=camera.overlay_right_custom,
                    overlay_text_scale=camera.overlay_text_scale,
                )
            
            # Start the camera
            success = server.start_camera(camera_id)
            self.write_json({
                "status": "ok" if success else "error",
                "camera": server.get_camera_status(camera_id)
            })
        
        elif action == "stop":
            # Check if this camera uses Motion - if so, we don't need to stop anything
            camera = self.config_store.get_camera(camera_id)
            stream_source = camera.stream_source if camera else "auto"
            motion_running = False
            if platform.system().lower() == "linux":
                motion_port = camera.motion_stream_port if camera else 8081
                motion_running = system_info.is_motion_running(motion_port)
            
            use_motion = stream_source == "motion" or (stream_source == "auto" and motion_running)
            
            if use_motion:
                # Motion is managing the stream, nothing to stop on our side
                logger.debug("MJPEG stop: Camera %s uses Motion, no internal server to stop", camera_id)
                self.write_json({
                    "status": "ok",
                    "camera": {
                        "camera_id": camera_id,
                        "is_running": False,
                        "stream_source": "motion",
                    }
                })
                return
            
            # Stop internal MJPEG server
            success = server.stop_camera(camera_id)
            self.write_json({
                "status": "ok" if success else "error",
                "camera": server.get_camera_status(camera_id)
            })
        
        elif action == "stop_all":
            server.stop_all()
            self.write_json({"status": "ok"})
        
        else:
            self.write_json({"error": "Invalid action. Use: start, stop, stop_all"}, status=400)


class MeetingHandler(BaseHandler):
    """Control Meeting API integration - heartbeat service."""
    
    async def get(self) -> None:
        """Get status of Meeting service."""
        svc = meeting_service.get_meeting_service()
        config = self.config_store.get_meeting_config()
        status = svc.get_status()
        
        self.write_json({
            "aiohttp_available": meeting_service.is_aiohttp_available(),
            "config": config,
            "service": status  # Use 'service' key for consistency with POST responses
        })
    
    async def post(self) -> None:
        """Control Meeting service - start/stop/heartbeat."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        action = payload.get("action", "")
        
        service = meeting_service.get_meeting_service()
        config = self.config_store.get_meeting_config()
        
        if action == "start":
            # Set callbacks for dynamic data
            service.set_callbacks(
                get_cameras=self.config_store.get_cameras,
                get_http_port=lambda: 8765  # Could be made configurable
            )
            # Configure service from current config
            service.configure(
                server_url=config["server_url"],
                device_key=config["device_key"],
                token_code=config["token_code"],
                heartbeat_interval=config["heartbeat_interval"]
            )
            success = await service.start()
            self.write_json({
                "status": "ok" if success else "error",
                "service": service.get_status()
            })
        
        elif action == "stop":
            await service.stop()
            self.write_json({
                "status": "ok",
                "service": service.get_status()
            })
        
        elif action == "heartbeat":
            # Send manual heartbeat
            # Reconfigure in case settings changed
            service.configure(
                server_url=config["server_url"],
                device_key=config["device_key"],
                token_code=config["token_code"],
                heartbeat_interval=config["heartbeat_interval"]
            )
            result = await service.send_manual_heartbeat()
            self.write_json({
                "status": "ok" if result["success"] else "error",
                "result": result,
                "service": service.get_status()
            })
        
        elif action == "configure":
            # Update configuration and restart if needed
            was_running = service.get_status()["is_running"]
            
            if was_running:
                await service.stop()
            
            service.configure(
                server_url=config["server_url"],
                device_key=config["device_key"],
                token_code=config["token_code"],
                heartbeat_interval=config["heartbeat_interval"]
            )
            
            # Auto-start if configured (always on)
            if service.is_configured():
                await service.start()
            
            self.write_json({
                "status": "ok",
                "service": service.get_status()
            })
        
        else:
            self.write_json({"error": "Invalid action. Use: start, stop, heartbeat, configure"}, status=400)


# ====================
# User Management Handlers
# ====================

class PasswordChangeHandler(BaseHandler):
    """Handler for changing user password."""
    
    @tornado.web.authenticated
    async def post(self) -> None:
        """Change the current user's password."""
        try:
            data = tornado.escape.json_decode(self.request.body)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, status=400)
            return
        
        current_password = data.get("current_password", "")
        new_password = data.get("new_password", "")
        confirm_password = data.get("confirm_password", "")
        
        if not current_password or not new_password:
            self.write_json({"error": "Mot de passe actuel et nouveau requis"}, status=400)
            return
        
        if new_password != confirm_password:
            self.write_json({"error": "Les nouveaux mots de passe ne correspondent pas"}, status=400)
            return
        
        if len(new_password) < 6:
            self.write_json({"error": "Le nouveau mot de passe doit contenir au moins 6 caractères"}, status=400)
            return
        
        username = self.get_current_user()
        if not username:
            self.write_json({"error": "Non authentifié"}, status=401)
            return
        
        success, message = self.user_manager.change_password(username, current_password, new_password)
        
        if success:
            self.write_json({"status": "ok", "message": "Mot de passe modifié avec succès"})
        else:
            self.write_json({"error": message}, status=400)


class CurrentUserHandler(BaseHandler):
    """Handler for getting current user info."""
    
    @tornado.web.authenticated
    async def get(self) -> None:
        """Get info about the current user."""
        user = self.get_current_user_info()
        if not user:
            self.write_json({"error": "Non authentifié"}, status=401)
            return
        
        self.write_json({
            "username": user.username,
            "role": user.role.value,
            "enabled": user.enabled,
            "must_change_password": user.must_change_password,
            "created_at": user.created_at,
            "last_login": user.last_login
        })


class UserHandler(BaseHandler):
    """Handler for user management (admin only)."""
    
    @tornado.web.authenticated
    async def get(self) -> None:
        """List all users (admin only)."""
        if not self.is_admin():
            self.write_json({"error": "Admin access required"}, status=403)
            return
        
        users = self.user_manager.list_users()
        user_list = []
        for user in users:
            user_list.append({
                "username": user.username,
                "role": user.role.value,
                "enabled": user.enabled,
                "must_change_password": user.must_change_password,
                "created_at": user.created_at,
                "last_login": user.last_login
            })
        
        self.write_json({"users": user_list})
    
    @tornado.web.authenticated
    async def post(self) -> None:
        """Create a new user (admin only)."""
        if not self.is_admin():
            self.write_json({"error": "Admin access required"}, status=403)
            return
        
        try:
            data = tornado.escape.json_decode(self.request.body)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, status=400)
            return
        
        username = data.get("username", "").strip()
        password = data.get("password", "")
        role_str = data.get("role", "user")
        must_change = data.get("must_change_password", True)
        
        if not username or not password:
            self.write_json({"error": "Nom d'utilisateur et mot de passe requis"}, status=400)
            return
        
        if len(password) < 6:
            self.write_json({"error": "Le mot de passe doit contenir au moins 6 caractères"}, status=400)
            return
        
        try:
            role = UserRole(role_str)
        except ValueError:
            role = UserRole.USER
        
        user = self.user_manager.create_user(
            username=username,
            password=password,
            role=role,
            must_change_password=must_change
        )
        
        if user:
            self.write_json({
                "status": "ok",
                "message": f"Utilisateur '{username}' créé",
                "user": {
                    "username": user.username,
                    "role": user.role.value,
                    "enabled": user.enabled,
                    "must_change_password": user.must_change_password
                }
            })
        else:
            self.write_json({"error": f"Impossible de créer l'utilisateur (existe déjà ?)"}, status=400)
    
    @tornado.web.authenticated
    async def delete(self) -> None:
        """Delete a user (admin only)."""
        if not self.is_admin():
            self.write_json({"error": "Admin access required"}, status=403)
            return
        
        try:
            data = tornado.escape.json_decode(self.request.body)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, status=400)
            return
        
        username = data.get("username", "").strip()
        if not username:
            self.write_json({"error": "Nom d'utilisateur requis"}, status=400)
            return
        
        # Prevent deleting self
        if username == self.get_current_user():
            self.write_json({"error": "Impossible de supprimer son propre compte"}, status=400)
            return
        
        if self.user_manager.delete_user(username):
            self.write_json({"status": "ok", "message": f"Utilisateur '{username}' supprimé"})
        else:
            self.write_json({"error": f"Utilisateur '{username}' non trouvé"}, status=404)


class UserPasswordResetHandler(BaseHandler):
    """Handler for admin to reset user password."""
    
    @tornado.web.authenticated
    async def post(self) -> None:
        """Reset a user's password (admin only)."""
        if not self.is_admin():
            self.write_json({"error": "Admin access required"}, status=403)
            return
        
        try:
            data = tornado.escape.json_decode(self.request.body)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, status=400)
            return
        
        username = data.get("username", "").strip()
        new_password = data.get("new_password", "")
        force_change = data.get("must_change_password", True)
        
        if not username or not new_password:
            self.write_json({"error": "Nom d'utilisateur et nouveau mot de passe requis"}, status=400)
            return
        
        if len(new_password) < 6:
            self.write_json({"error": "Le mot de passe doit contenir au moins 6 caractères"}, status=400)
            return
        
        if self.user_manager.admin_reset_password(username, new_password, force_change):
            self.write_json({
                "status": "ok",
                "message": f"Mot de passe de '{username}' réinitialisé"
            })
        else:
            self.write_json({"error": f"Utilisateur '{username}' non trouvé"}, status=404)


class UserEnableHandler(BaseHandler):
    """Handler for enabling/disabling users."""
    
    @tornado.web.authenticated
    async def post(self) -> None:
        """Enable or disable a user (admin only)."""
        if not self.is_admin():
            self.write_json({"error": "Admin access required"}, status=403)
            return
        
        try:
            data = tornado.escape.json_decode(self.request.body)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, status=400)
            return
        
        username = data.get("username", "").strip()
        enabled = data.get("enabled", True)
        
        if not username:
            self.write_json({"error": "Nom d'utilisateur requis"}, status=400)
            return
        
        # Prevent disabling self
        if username == self.get_current_user() and not enabled:
            self.write_json({"error": "Impossible de désactiver son propre compte"}, status=400)
            return
        
        user = self.user_manager.enable_user(username, enabled)
        if user:
            status_text = "activé" if enabled else "désactivé"
            self.write_json({
                "status": "ok",
                "message": f"Utilisateur '{username}' {status_text}"
            })
        else:
            self.write_json({"error": f"Utilisateur '{username}' non trouvé"}, status=404)


# =====================================================
# Audio Device Handlers
# =====================================================

class AudioDetectHandler(BaseHandler):
    """Detect available audio input devices on the system."""
    
    async def get(self) -> None:
        """Get list of detected audio devices.
        
        Query params:
            include_filtered: if "true", include devices matching filter patterns
        """
        include_filtered = self.get_argument("include_filtered", "false").lower() == "true"
        
        # Get filter patterns from config
        filter_patterns = self.config_store.get_audio_filter_patterns()
        
        # Update detector with current patterns
        detector = audio_detector.get_detector()
        detector.filter_patterns = filter_patterns
        
        # Detect audio devices
        devices = detector.detect_devices(include_filtered=include_filtered)
        
        self.write_json({
            "devices": [d.to_dict() for d in devices],
            "filter_patterns": filter_patterns,
            "platform": detector._system,
        })


class AudioFilterPatternsHandler(BaseHandler):
    """Manage audio filter patterns."""
    
    async def get(self) -> None:
        """Get current audio filter patterns."""
        patterns = self.config_store.get_audio_filter_patterns()
        self.write_json({"patterns": patterns})
    
    async def post(self) -> None:
        """Set audio filter patterns."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        patterns = payload.get("patterns", [])
        
        if not isinstance(patterns, list):
            self.write_json({"error": "patterns must be a list"}, status=400)
            return
        
        self.config_store.set_audio_filter_patterns(patterns)
        self.write_json({"status": "ok", "patterns": patterns})
    
    async def put(self) -> None:
        """Add an audio filter pattern."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        pattern = payload.get("pattern", "")
        
        if not pattern:
            self.write_json({"error": "pattern is required"}, status=400)
            return
        
        self.config_store.add_audio_filter_pattern(pattern)
        self.write_json({"status": "ok", "patterns": self.config_store.get_audio_filter_patterns()})
    
    async def delete(self) -> None:
        """Remove an audio filter pattern."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        pattern = payload.get("pattern", "")
        
        if not pattern:
            self.write_json({"error": "pattern is required"}, status=400)
            return
        
        self.config_store.remove_audio_filter_pattern(pattern)
        self.write_json({"status": "ok", "patterns": self.config_store.get_audio_filter_patterns()})


class AudioListHandler(BaseHandler):
    """List configured audio devices."""
    
    async def get(self) -> None:
        self.write_json({"audio_devices": self.config_store.get_audio_devices()})


class AudioConfigHandler(BaseHandler):
    """Handle audio device configuration."""
    
    async def get(self, audio_id: str) -> None:
        """Get configuration of an audio device."""
        audio = self.config_store.get_audio_device(audio_id)
        if not audio:
            self.write_json({"error": "Audio device not found"}, status=404)
            return
        self.write_json(audio.to_dict())

    async def post(self, audio_id: str) -> None:
        """Update audio device configuration."""
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        
        try:
            result = self.config_store.save_audio_config(audio_id, payload)
        except KeyError:
            self.write_json({"error": "Audio device not found"}, status=404)
            return
        
        self.write_json(result)


class AudioConfigSectionsHandler(BaseHandler):
    """Return audio configuration sections for dynamic UI rendering."""
    
    async def get(self, audio_id: str) -> None:
        sections = self.config_store.get_audio_config_sections(audio_id)
        if not sections:
            self.write_json({"error": "Audio device not found"}, status=404)
            return
        self.write_json({"sections": sections})


class AudioAddHandler(BaseHandler):
    """Handle audio device addition requests."""
    
    async def post(self) -> None:
        payload = tornado.escape.json_decode(self.request.body or b"{}")
        name = payload.get("name", "")
        device_id = payload.get("device_id", "")
        
        result = self.config_store.add_audio_device(name=name, device_id=device_id)
        self.write_json(result, status=201)


class AudioDeleteHandler(BaseHandler):
    """Handle audio device deletion requests."""
    
    async def delete(self, audio_id: str) -> None:
        try:
            result = self.config_store.remove_audio_device(audio_id)
            self.write_json(result)
        except KeyError:
            self.write_json({"error": "Audio device not found"}, status=404)


# ============================================================================
# RTSP Stream Handlers
# ============================================================================

class RTSPStatusHandler(BaseHandler):
    """Handler for RTSP server status."""
    
    async def get(self) -> None:
        """Get RTSP server status and FFmpeg availability."""
        server = rtsp_server.get_rtsp_server()
        
        self.write_json({
            "ffmpeg_available": server.is_ffmpeg_available(),
            "ffmpeg_version": server.get_ffmpeg_version(),
            "rtsp_server_available": server.is_rtsp_server_available(),
            "streams": {
                cam_id: {
                    "camera_id": status.camera_id,
                    "is_running": status.is_running,
                    "rtsp_url": status.rtsp_url,
                    "has_audio": status.has_audio,
                    "error": status.error,
                    "started_at": status.started_at,
                }
                for cam_id, status in server.get_all_stream_status().items()
            }
        })


class RTSPStreamHandler(BaseHandler):
    """Handler for individual RTSP stream control."""
    
    async def get(self, camera_id: str) -> None:
        """Get RTSP stream status for a specific camera."""
        server = rtsp_server.get_rtsp_server()
        status = server.get_stream_status(camera_id)
        
        if status:
            self.write_json({
                "camera_id": status.camera_id,
                "is_running": status.is_running,
                "rtsp_url": status.rtsp_url,
                "has_audio": status.has_audio,
                "error": status.error,
                "started_at": status.started_at,
            })
        else:
            self.write_json({
                "camera_id": camera_id,
                "is_running": False,
                "rtsp_url": "",
                "has_audio": False,
                "error": None,
                "started_at": None,
            })
    
    async def post(self, camera_id: str) -> None:
        """Start or stop RTSP stream for a camera."""
        server = rtsp_server.get_rtsp_server()
        
        if not server.is_ffmpeg_available():
            self.write_json({"error": "FFmpeg not available"}, status=500)
            return
            
        try:
            data = tornado.escape.json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            data = {}
            
        action = data.get("action", "start")
        
        if action == "start":
            # Get camera config
            camera = self.config_store.get_camera(camera_id)
            if not camera:
                self.write_json({"error": "Camera not found"}, status=404)
                return
                
            # Find linked audio device from camera's rtsp_audio_device setting
            audio_device = None
            if camera.rtsp_audio_device:
                audio_device = self.config_store.get_audio_device(camera.rtsp_audio_device)
                    
            # Build stream config
            rtsp_port = server.get_rtsp_port_for_camera(camera_id)
            
            config = rtsp_server.RTSPStreamConfig(
                camera_id=camera_id,
                camera_device=camera.device_settings.get("device", "0"),
                camera_name=camera.name,
                resolution=camera.resolution,
                framerate=camera.framerate,
                video_bitrate=data.get("video_bitrate", 2000),
                rtsp_port=rtsp_port,
                rtsp_path=f"/cam{camera_id}",
            )
            
            # Add audio if linked device exists
            if audio_device:
                config.audio_device_id = audio_device.device_id
                config.audio_device_name = audio_device.name
                config.audio_sample_rate = audio_device.sample_rate
                config.audio_channels = audio_device.channels
                config.audio_bitrate = audio_device.bitrate
                config.audio_codec = audio_device.codec
                
            status = await server.start_stream(config)
            
            self.write_json({
                "status": "ok" if status.is_running else "error",
                "camera_id": status.camera_id,
                "is_running": status.is_running,
                "rtsp_url": status.rtsp_url,
                "has_audio": status.has_audio,
                "rtsp_port": rtsp_port,
                "error": status.error,
            })
            
        elif action == "stop":
            success = await server.stop_stream(camera_id)
            self.write_json({
                "status": "ok" if success else "error",
                "camera_id": camera_id,
                "is_running": False,
            })
            
        else:
            self.write_json({"error": f"Unknown action: {action}"}, status=400)


class HLSProxyHandler(BaseHandler):
    """Proxy handler for HLS streams from MediaMTX.
    
    MediaMTX serves HLS on port 8888, but we proxy through our server
    to avoid CORS issues and provide unified access.
    """
    
    MEDIAMTX_HLS_PORT = 8888
    
    async def get(self, path: str) -> None:
        """Proxy HLS requests to MediaMTX."""
        import aiohttp
        
        mediamtx_url = f"http://127.0.0.1:{self.MEDIAMTX_HLS_PORT}/{path}"
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(mediamtx_url) as response:
                    if response.status != 200:
                        logger.debug("HLS proxy: MediaMTX returned %d for %s", response.status, path)
                        self.set_status(response.status)
                        self.write(await response.text())
                        return
                    
                    # Set appropriate content type
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
                    self.set_header("Content-Type", content_type)
                    
                    # CORS headers for video playback
                    self.set_header("Access-Control-Allow-Origin", "*")
                    self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                    self.set_header("Access-Control-Allow-Headers", "Content-Type")
                    
                    # Cache control for HLS segments
                    if path.endswith(".m3u8"):
                        # Playlist files should not be cached long
                        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    elif path.endswith(".ts"):
                        # Video segments can be cached briefly
                        self.set_header("Cache-Control", "public, max-age=2")
                    
                    # Stream the content
                    self.write(await response.read())
                    
        except aiohttp.ClientConnectorError:
            logger.warning("HLS proxy: Cannot connect to MediaMTX on port %d", self.MEDIAMTX_HLS_PORT)
            self.set_status(503)
            self.write_json({"error": "HLS server not available", "hint": "MediaMTX may not be running"})
        except Exception as e:
            logger.error("HLS proxy error: %s", e)
            self.set_status(500)
            self.write_json({"error": str(e)})
    
    def options(self, path: str) -> None:
        """Handle CORS preflight requests."""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
        self.set_status(204)


# ============================================================================
# Update Handler
# ============================================================================

class UpdateHandler(BaseHandler):
    """Handler for checking and performing updates from GitHub."""
    
    async def get(self) -> None:
        """
        Check for available updates.
        
        Query params:
            include_prereleases: If "true", include prerelease versions.
            source: If "true", check source (branch) info instead of releases.
            branch: Branch name for source check (default: "main").
        """
        source_mode = self.get_query_argument("source", "false").lower() == "true"
        
        if source_mode:
            # Check source (branch) info
            branch = self.get_query_argument("branch", "main")
            try:
                source_info = await updater.trigger_source_check(branch)
                self.write_json(source_info)
            except Exception as e:
                self.write_json({
                    "error": str(e),
                    "current_version": updater.get_current_version(),
                    "branch": branch,
                }, status=500)
        else:
            # Check releases
            include_prereleases = self.get_query_argument("include_prereleases", "false").lower() == "true"
            try:
                check_result = await updater.trigger_update_check(include_prereleases)
                self.write_json(check_result.to_dict())
            except Exception as e:
                self.write_json({
                    "error": str(e),
                    "current_version": updater.get_current_version(),
                    "update_available": False,
                }, status=500)
    
    async def post(self) -> None:
        """
        Trigger an update.
        
        POST body (JSON):
            action: "check", "update", "check_source", "update_source", or "status"
            include_prereleases: boolean (default: false) - for release updates
            branch: string (default: "main") - for source updates
        """
        try:
            data = tornado.escape.json_decode(self.request.body) if self.request.body else {}
        except json.JSONDecodeError:
            data = {}
        
        action = data.get("action", "check")
        include_prereleases = data.get("include_prereleases", False)
        branch = data.get("branch", "main")
        
        if action == "check":
            # Check for release updates
            check_result = await updater.trigger_update_check(include_prereleases)
            self.write_json(check_result.to_dict())
            
        elif action == "update":
            # Perform release update
            update_result = await updater.trigger_update(include_prereleases)
            status = 200 if update_result.success else 500
            self.write_json(update_result.to_dict(), status=status)
            
        elif action == "check_source":
            # Check source (branch) info
            source_info = await updater.trigger_source_check(branch)
            self.write_json(source_info)
            
        elif action == "update_source":
            # Perform source update from branch
            update_result = await updater.trigger_source_update(branch)
            status = 200 if update_result.success else 500
            self.write_json(update_result.to_dict(), status=status)
            
        elif action == "status":
            # Get current update status
            status = await updater.get_update_status()
            self.write_json(status)
            
        else:
            self.write_json({"error": f"Unknown action: {action}"}, status=400)


# ============================================================================
# Service Control Handler
# ============================================================================

class ServiceRestartHandler(BaseHandler):
    """Handler for restarting the service (Linux only)."""
    
    async def post(self) -> None:
        """
        Restart the motion-frontend service.
        
        Only works on Linux with systemd.
        """
        import platform
        import subprocess
        import asyncio
        
        if platform.system() != "Linux":
            self.write_json({
                "success": False,
                "error": "Service restart is only available on Linux"
            }, status=400)
            return
        
        try:
            # Schedule the restart after sending response
            async def delayed_restart():
                await asyncio.sleep(1)  # Give time for response to be sent
                subprocess.run(
                    ["sudo", "systemctl", "restart", "motion-frontend"],
                    check=False
                )
            
            # Start the delayed restart
            asyncio.create_task(delayed_restart())
            
            self.write_json({
                "success": True,
                "message": "Service restart initiated. Please wait..."
            })
        except Exception as e:
            self.write_json({
                "success": False,
                "error": str(e)
            }, status=500)


# ============================================================================
# Log Download Handler
# ============================================================================

class LogDownloadHandler(BaseHandler):
    """Handler for downloading log files."""
    
    async def get(self) -> None:
        """Download the current log file."""
        from pathlib import Path
        
        log_file = Path(__file__).parent.parent / "logs" / "motion_frontend.log"
        
        if not log_file.exists():
            self.set_status(404)
            self.write_json({"error": "Log file not found"})
            return
        
        try:
            # Read log content
            log_content = log_file.read_text(encoding="utf-8", errors="replace")
            
            # Set headers for file download
            self.set_header("Content-Type", "text/plain; charset=utf-8")
            self.set_header(
                "Content-Disposition",
                f'attachment; filename="motion_frontend_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log"'
            )
            
            self.write(log_content)
        except Exception as e:
            self.set_status(500)
            self.write_json({"error": str(e)})


HANDLER_EXPORTS = [
    MainHandler,
    LoginHandler,
    LogoutHandler,
    VersionHandler,
    ConfigMainHandler,
    ConfigListHandler,
    ConfigCameraHandler,
    CameraAddHandler,
    CameraDeleteHandler,
    CameraConfigSectionsHandler,
    CameraDetectHandler,
    CameraFilterPatternsHandler,
    CameraCapabilitiesHandler,
    CameraControlsHandler,
    LoggingConfigHandler,
    HealthHandler,
    FrameHandler,
    MJPEGStreamHandler,
    MJPEGControlHandler,
    MeetingHandler,
    PasswordChangeHandler,
    CurrentUserHandler,
    UserHandler,
    UserPasswordResetHandler,
    UserEnableHandler,
    # Audio handlers
    AudioDetectHandler,
    AudioFilterPatternsHandler,
    AudioListHandler,
    AudioConfigHandler,
    AudioConfigSectionsHandler,
    AudioAddHandler,
    AudioDeleteHandler,
    # RTSP handlers
    RTSPStatusHandler,
    RTSPStreamHandler,
    HLSProxyHandler,
    # Update handler
    UpdateHandler,
    # Service control handlers
    ServiceRestartHandler,
    LogDownloadHandler,
]
