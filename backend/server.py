# File Version: 0.19.4
from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple, Type

import tornado.httpserver
import tornado.ioloop
import tornado.web

from .config_store import ConfigStore
from . import updater
from .handlers import (
    CameraAddHandler,
    CameraCapabilitiesHandler,
    CameraConfigSectionsHandler,
    CameraControlsHandler,
    CameraDeleteHandler,
    CameraDetectHandler,
    CameraFilterPatternsHandler,
    ConfigCameraHandler,
    ConfigListHandler,
    ConfigMainHandler,
    CurrentUserHandler,
    FrameHandler,
    HealthHandler,
    LogDownloadHandler,
    LoggingConfigHandler,
    LoginHandler,
    LogoutHandler,
    MainHandler,
    MeetingHandler,
    MJPEGControlHandler,
    MJPEGStreamHandler,
    PasswordChangeHandler,
    ServiceRestartHandler,
    UpdateHandler,
    UserEnableHandler,
    UserHandler,
    UserPasswordResetHandler,
    VersionHandler,
    # Audio handlers
    AudioAddHandler,
    AudioConfigHandler,
    AudioConfigSectionsHandler,
    AudioDeleteHandler,
    AudioDetectHandler,
    AudioFilterPatternsHandler,
    AudioListHandler,
    # RTSP handlers
    RTSPStatusHandler,
    RTSPStreamHandler,
    HLSProxyHandler,
)
from .jinja import build_environment
from .settings import ServerSettings

Route = Tuple[str, Type[tornado.web.RequestHandler], Optional[dict]]


def _resolve_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _detect_version(changelog_path: Path) -> str:
    try:
        with changelog_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("## "):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
    except FileNotFoundError:
        logging.warning("Changelog not found at %s", changelog_path)
    return "dev"


def _build_routes(static_path: Path) -> Sequence[Route]:
    return [
        (r"/", MainHandler, None),
        (r"/login/?", LoginHandler, None),
        (r"/logout/?", LogoutHandler, None),
        (r"/version/?", VersionHandler, None),
        (r"/api/config/main/?", ConfigMainHandler, None),
        (r"/api/config/list/?", ConfigListHandler, None),
        # Camera routes
        (r"/api/config/camera/add/?", CameraAddHandler, None),
        (r"/api/config/camera/(?P<camera_id>[\w-]+)/sections/?", CameraConfigSectionsHandler, None),
        (r"/api/config/camera/(?P<camera_id>[\w-]+)/?", ConfigCameraHandler, None),
        (r"/api/config/camera/(?P<camera_id>[\w-]+)/delete/?", CameraDeleteHandler, None),
        (r"/api/cameras/detect/?", CameraDetectHandler, None),
        (r"/api/cameras/capabilities/(?P<device_path>.+)/?", CameraCapabilitiesHandler, None),
        (r"/api/cameras/controls/(?P<device_path>.+)/?", CameraControlsHandler, None),
        (r"/api/cameras/filters/?", CameraFilterPatternsHandler, None),
        # Audio routes
        (r"/api/config/audio/add/?", AudioAddHandler, None),
        (r"/api/config/audio/list/?", AudioListHandler, None),
        (r"/api/config/audio/(?P<audio_id>[\w-]+)/sections/?", AudioConfigSectionsHandler, None),
        (r"/api/config/audio/(?P<audio_id>[\w-]+)/?", AudioConfigHandler, None),
        (r"/api/config/audio/(?P<audio_id>[\w-]+)/delete/?", AudioDeleteHandler, None),
        (r"/api/audio/detect/?", AudioDetectHandler, None),
        (r"/api/audio/filters/?", AudioFilterPatternsHandler, None),
        # RTSP routes
        (r"/api/rtsp/?", RTSPStatusHandler, None),
        (r"/api/rtsp/(?P<camera_id>[\w-]+)/?", RTSPStreamHandler, None),
        # HLS proxy route (proxies to MediaMTX on port 8888)
        (r"/hls/(?P<path>.*)/?", HLSProxyHandler, None),
        # Other API routes
        (r"/api/mjpeg/?", MJPEGControlHandler, None),
        (r"/api/meeting/?", MeetingHandler, None),
        (r"/api/logging/?", LoggingConfigHandler, None),
        (r"/api/update/?", UpdateHandler, None),
        (r"/api/service/restart/?", ServiceRestartHandler, None),
        (r"/api/logs/download/?", LogDownloadHandler, None),
        # User management routes
        (r"/api/user/me/?", CurrentUserHandler, None),
        (r"/api/user/password/?", PasswordChangeHandler, None),
        (r"/api/users/?", UserHandler, None),
        (r"/api/users/reset-password/?", UserPasswordResetHandler, None),
        (r"/api/users/enable/?", UserEnableHandler, None),
        (r"/health/?", HealthHandler, None),
        (r"/frame/(?P<camera_id>[\w-]+)/?", FrameHandler, None),
        (r"/stream/(?P<camera_id>[\w-]+)/?", MJPEGStreamHandler, None),
        (
            r"/static/(.*)",
            tornado.web.StaticFileHandler,
            {"path": str(static_path)},
        ),
    ]


def build_application(settings: ServerSettings, config_store: Optional[ConfigStore] = None) -> tornado.web.Application:
    if not settings.template_path.exists():
        raise FileNotFoundError(f"Template directory missing: {settings.template_path}")
    if not settings.static_path.exists():
        raise FileNotFoundError(f"Static directory missing: {settings.static_path}")

    store = config_store or ConfigStore()
    jinja_env = build_environment(settings.template_path)
    version = _detect_version(settings.changelog_path)

    app_settings = {
        "debug": settings.environment != "production",
        "template_path": str(settings.template_path),
        "static_path": str(settings.static_path),
        "config_store": store,
        "jinja_env": jinja_env,
        "frontend_version": version,
        "git_commit": settings.environment,
        "cookie_secret": "motion_frontend_dev_secret_change_in_production_2024",
        "login_url": "/login",
    }
    routes = _build_routes(settings.static_path)
    return tornado.web.Application(routes, **app_settings)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Motion Frontend Tornado server")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind", metavar="ADDR")
    parser.add_argument("--port", default=8765, type=int, help="Port to listen on")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="Project root path")
    parser.add_argument("--template-path", default="templates", help="Relative or absolute template path")
    parser.add_argument("--static-path", default="static", help="Relative or absolute static asset path")
    parser.add_argument("--changelog", default="CHANGELOG.md", help="Relative or absolute changelog path")
    parser.add_argument("--environment", default="development", help="Environment label (development/production/staging)")
    parser.add_argument("--log-level", default="INFO", choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"], help="Python logging level")
    return parser.parse_args(argv)


from logging.handlers import RotatingFileHandler


# Default log file path
LOG_FILE_PATH = Path(__file__).parent.parent / "logs" / "motion_frontend.log"


def _configure_logging(level: str, log_to_file: bool = True, reset_on_start: bool = False) -> None:
    """Configure logging with console and optional file output.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_to_file: Whether to write logs to a file.
        reset_on_start: Whether to clear the log file on startup.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
    
    # Create logs directory if needed
    if log_to_file:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Reset log file if requested
        if reset_on_start and LOG_FILE_PATH.exists():
            try:
                LOG_FILE_PATH.unlink()
            except PermissionError:
                # File is in use by another process, skip reset
                pass
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)
    
    # Reduce tornado.access verbosity - only WARNING and above in INFO mode
    # In DEBUG mode, show all tornado.access logs
    tornado_access_logger = logging.getLogger("tornado.access")
    if log_level > logging.DEBUG:
        # In INFO or higher, tornado.access only shows warnings/errors
        tornado_access_logger.setLevel(logging.WARNING)
    else:
        # In DEBUG mode, show all access logs
        tornado_access_logger.setLevel(logging.DEBUG)
    
    # File handler (rotating, max 5MB, keep 3 backups)
    if log_to_file:
        file_handler = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(file_handler)
        logging.info("Logging to file: %s", LOG_FILE_PATH)


def _attach_signal_handlers(server: tornado.httpserver.HTTPServer, loop: tornado.ioloop.IOLoop) -> None:
    def _graceful_stop(signum: int, _frame: object) -> None:
        logging.info("Signal %s received, initiating graceful shutdown...", signum)
        
        # Stop MJPEG server first to release camera resources and ports
        try:
            from . import mjpeg_server
            mjpeg = mjpeg_server.get_mjpeg_server()
            if mjpeg:
                logging.info("Stopping all MJPEG streams...")
                mjpeg.stop_all()
                logging.info("MJPEG streams stopped")
        except Exception as e:
            logging.error("Error stopping MJPEG server: %s", e)
        
        # Stop RTSP server
        try:
            from . import rtsp_server
            rtsp = rtsp_server.get_rtsp_server()
            if rtsp:
                logging.info("Stopping all RTSP streams...")
                rtsp.stop_all()
                logging.info("RTSP streams stopped")
        except Exception as e:
            logging.error("Error stopping RTSP server: %s", e)
        
        # Stop Meeting service
        try:
            from . import meeting_service
            svc = meeting_service.get_meeting_service()
            if svc:
                logging.info("Stopping Meeting service...")
                svc.stop()
                logging.info("Meeting service stopped")
        except Exception as e:
            logging.error("Error stopping Meeting service: %s", e)
        
        # Now stop the HTTP server
        server.stop()
        logging.info("HTTP server stopped, scheduling IOLoop stop...")
        loop.add_timeout(loop.time() + 0.5, loop.stop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _graceful_stop)
        except ValueError:
            logging.warning("Unable to bind signal %s", sig)


async def _start_rtsp_streams_on_boot(config_store: ConfigStore) -> None:
    """Start RTSP streams for cameras that have rtsp_enabled=True on server boot."""
    from . import rtsp_server
    from . import mjpeg_server
    from . import system_info
    from .config_store import resolve_video_device, resolve_audio_device
    import platform
    
    rtsp = rtsp_server.get_rtsp_server()
    if not rtsp.is_ffmpeg_available():
        logging.warning("FFmpeg not available, skipping RTSP auto-start")
        return
    
    # On Linux, check if Motion is running - if so, warn but don't block
    is_linux = platform.system().lower() == "linux"
    motion_running = False
    if is_linux:
        motion_running = system_info.is_motion_running()
        if motion_running:
            logging.warning("Motion daemon is running - RTSP streams may fail if Motion is using the cameras")
    
    mjpeg = mjpeg_server.get_mjpeg_server()
    
    cameras = config_store.get_cameras()
    for cam_info in cameras:
        cam = config_store.get_camera(cam_info["id"])
        if cam and cam.rtsp_enabled:
            logging.info("Auto-starting RTSP stream for camera %s (%s)", cam.identifier, cam.name)
            
            # Warn about Motion conflict
            if motion_running:
                motion_port = cam.motion_stream_port or 8081
                logging.warning("Camera %s: Motion may be using this device (port %d)", cam.identifier, motion_port)
            
            try:
                # Stop MJPEG stream first to release the camera (Windows can only have one process access camera)
                if mjpeg:
                    mjpeg.stop_camera(cam.identifier)
                    logging.debug("Stopped MJPEG stream for camera %s before RTSP start", cam.identifier)
                
                rtsp_port = rtsp.get_rtsp_port_for_camera(cam.identifier)
                
                # Resolve the actual device path using stable path if available
                device_path = cam.device_settings.get("device", "0")
                stable_path = cam.device_settings.get("stable_device_path", "")
                resolved_device = resolve_video_device(device_path, stable_path)
                
                logging.debug("Camera %s device resolution: %s (stable: %s) -> %s", 
                            cam.identifier, device_path, stable_path, resolved_device)
                
                config = rtsp_server.RTSPStreamConfig(
                    camera_id=cam.identifier,
                    camera_device=resolved_device,
                    camera_name=cam.name,
                    resolution=cam.resolution,
                    framerate=cam.framerate,
                    video_bitrate=2000,
                    rtsp_port=rtsp_port,
                    rtsp_path=f"/cam{cam.identifier}",
                )
                
                # Add audio if configured
                if cam.rtsp_audio_device:
                    audio = config_store.get_audio_device(cam.rtsp_audio_device)
                    if audio and audio.enabled:
                        # Resolve audio device using stable ID
                        audio_device = audio.device_id
                        stable_audio = audio.device_settings.get("stable_id", "")
                        resolved_audio = resolve_audio_device(audio_device, stable_audio)
                        
                        logging.debug("Audio device resolution: %s (stable: %s) -> %s",
                                    audio_device, stable_audio, resolved_audio)
                        
                        config.audio_device_id = resolved_audio
                        config.audio_device_name = audio.name
                        config.audio_sample_rate = audio.sample_rate
                        config.audio_channels = audio.channels
                        config.audio_bitrate = audio.bitrate
                        config.audio_codec = audio.codec
                
                status = await rtsp.start_stream(config)
                if status.is_running:
                    logging.info("RTSP stream started for camera %s: %s", cam.identifier, status.rtsp_url)
                else:
                    logging.error("Failed to start RTSP stream for camera %s: %s", cam.identifier, status.error)
            except Exception as e:
                logging.error("Error starting RTSP stream for camera %s: %s", cam.identifier, e)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    
    # Load config to get logging settings
    config_store = ConfigStore()
    log_level = config_store.get_logging_level() or args.log_level
    log_to_file = config_store.get_log_to_file()
    log_reset_on_start = config_store.get_log_reset_on_start()
    
    _configure_logging(log_level, log_to_file, log_reset_on_start)

    # Display startup banner
    version = updater.get_current_version()
    banner = f"=========== Mme v{version} starting ==========="
    logging.info(banner)
    print(banner)  # Also print to stdout for interactive mode

    root = Path(args.root).resolve()
    settings = ServerSettings(
        host=args.host,
        port=args.port,
        template_path=_resolve_path(root, args.template_path),
        static_path=_resolve_path(root, args.static_path),
        environment=args.environment,
        changelog_path=_resolve_path(root, args.changelog),
    )

    app = build_application(settings, config_store)
    server = tornado.httpserver.HTTPServer(app)
    server.listen(settings.port, address=settings.host)

    loop = tornado.ioloop.IOLoop.current()
    _attach_signal_handlers(server, loop)

    logging.info("Motion Frontend listening on http://%s:%s", settings.host, settings.port)
    
    # Schedule RTSP auto-start after event loop starts
    loop.add_callback(lambda: loop.add_callback(_start_rtsp_streams_on_boot, config_store))

    try:
        loop.start()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received; shutting down")
    finally:
        server.stop()
        loop.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
