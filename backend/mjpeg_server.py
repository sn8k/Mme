# -*- coding: utf-8 -*-
"""
MJPEG streaming server for Motion Frontend.
Captures frames from cameras and streams them via HTTP multipart.
Each camera has its own dedicated HTTP server on a configurable port.

Version: 0.9.3
"""

import asyncio
import base64
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import AsyncGenerator, Dict, Optional, List, Callable, Any
from queue import Queue, Empty
import io

logger = logging.getLogger(__name__)

# Try to import OpenCV
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV not available. MJPEG streaming will be disabled.")


# Type for auth verification callback
AuthVerifyCallback = Callable[[str, str], bool]


@dataclass
class CameraStream:
    """Represents a camera stream configuration."""
    camera_id: str
    device_path: str  # Device index (0, 1, 2) or path (/dev/video0)
    name: str = "Camera"
    width: int = 640  # Capture width (input)
    height: int = 480  # Capture height (input)
    stream_width: int = 0  # Output width (0 = same as capture)
    stream_height: int = 0  # Output height (0 = same as capture)
    fps: int = 15
    quality: int = 80  # JPEG quality (1-100)
    mjpeg_port: int = 8081  # Dedicated MJPEG streaming port
    stream_auth_enabled: bool = False  # HTTP Basic authentication required
    stream_auth_verify: Optional[AuthVerifyCallback] = field(default=None, repr=False)  # Callback to verify credentials
    
    # Text overlay settings
    overlay_left_text: str = "disabled"  # camera_name, timestamp, custom, capture_info, disabled
    overlay_left_custom: str = ""
    overlay_right_text: str = "timestamp"
    overlay_right_custom: str = ""
    overlay_text_scale: int = 3  # 1-10
    
    # Runtime state
    capture: Any = field(default=None, repr=False)
    is_running: bool = False
    frame_count: int = 0
    last_frame: Optional[bytes] = None
    last_frame_time: float = 0
    last_frame_size: int = 0  # Size of last frame in bytes
    error: Optional[str] = None
    subscribers: List[Queue] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    # Stats tracking (for real-time FPS and bandwidth)
    _stats_start_time: float = field(default=0, repr=False)
    _stats_frame_count: int = field(default=0, repr=False)
    _stats_bytes_sent: int = field(default=0, repr=False)
    _real_fps: float = field(default=0, repr=False)
    _bandwidth_kbps: float = field(default=0, repr=False)
    
    # HTTP server for this camera's stream
    _http_server: Any = field(default=None, repr=False)
    _http_thread: Any = field(default=None, repr=False)


def create_mjpeg_handler(camera_stream: CameraStream):
    """Factory function to create an MJPEG stream handler for a specific camera."""
    
    class MJPEGStreamHandler(BaseHTTPRequestHandler):
        """HTTP request handler for dedicated MJPEG camera streams."""
        
        # Reference to the camera (set by factory)
        camera = camera_stream
        
        def log_message(self, format: str, *args) -> None:
            """Override to use our logger instead of stderr."""
            logger.debug("MJPEG HTTP [%s:%d] %s", 
                        self.camera.camera_id, self.camera.mjpeg_port,
                        format % args)
        
        def _check_auth(self) -> bool:
            """Check HTTP Basic authentication if enabled.
            
            Returns:
                True if authentication is not required or credentials are valid.
            """
            if not self.camera.stream_auth_enabled:
                return True
            
            if not self.camera.stream_auth_verify:
                logger.warning("MJPEG auth enabled but no verify callback for camera %s", 
                              self.camera.camera_id)
                return False
            
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Basic "):
                return False
            
            try:
                # Decode Base64 credentials
                encoded_credentials = auth_header[6:]  # Remove "Basic " prefix
                decoded = base64.b64decode(encoded_credentials).decode("utf-8")
                username, password = decoded.split(":", 1)
                
                # Verify credentials using callback (uses UserManager)
                if self.camera.stream_auth_verify(username, password):
                    return True
                    
                logger.warning("MJPEG auth failed for camera %s: invalid credentials for user '%s'", 
                              self.camera.camera_id, username)
                return False
            except Exception as e:
                logger.warning("MJPEG auth error for camera %s: %s", 
                              self.camera.camera_id, e)
                return False
        
        def _send_auth_required(self):
            """Send 401 Unauthorized response."""
            self.send_response(401)
            self.send_header("WWW-Authenticate", f'Basic realm="Camera {self.camera.camera_id} Stream"')
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>401 Unauthorized</h1><p>Authentication required</p></body></html>")
        
        def do_GET(self):
            """Handle GET requests for MJPEG stream."""
            # Check authentication if enabled
            if not self._check_auth():
                self._send_auth_required()
                return
            
            if self.path == "/stream/" or self.path == "/stream":
                self._stream_mjpeg()
            elif self.path == "/" or self.path == "/status":
                self._send_status()
            else:
                self.send_error(404, "Not Found")
        
        def _send_status(self):
            """Send a simple status page."""
            status_html = f"""<!DOCTYPE html>
<html>
<head><title>Camera {self.camera.camera_id} - {self.camera.name}</title></head>
<body>
<h1>Camera {self.camera.camera_id}: {self.camera.name}</h1>
<p>Status: {'Running' if self.camera.is_running else 'Stopped'}</p>
<p>Resolution: {self.camera.width}x{self.camera.height}</p>
<p>Stream: <a href="/stream/">/stream/</a></p>
<img src="/stream/" width="640" />
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(status_html)))
            self.end_headers()
            self.wfile.write(status_html.encode("utf-8"))
        
        def _stream_mjpeg(self):
            """Stream MJPEG frames continuously."""
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            logger.info("MJPEG client connected to camera %s on port %d", 
                       self.camera.camera_id, self.camera.mjpeg_port)
            
            frame_interval = 1.0 / max(1, self.camera.fps)
            last_frame_time = 0
            
            try:
                while self.camera.is_running:
                    current_time = time.time()
                    
                    # Rate limiting
                    if current_time - last_frame_time < frame_interval * 0.8:
                        time.sleep(0.01)
                        continue
                    
                    # Get current frame
                    frame = self.camera.last_frame
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    
                    # Send multipart frame
                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n".encode())
                        self.wfile.write(b"\r\n")
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                        
                        last_frame_time = current_time
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    except Exception as e:
                        logger.debug("Stream write error: %s", e)
                        break
                        
            except Exception as e:
                logger.debug("MJPEG stream ended: %s", e)
            finally:
                logger.info("MJPEG client disconnected from camera %s", self.camera.camera_id)
    
    return MJPEGStreamHandler


class MJPEGServer:
    """
    MJPEG streaming server that captures from cameras and provides HTTP streams.
    
    Usage:
        server = MJPEGServer()
        server.add_camera("1", "0", "Webcam", width=1280, height=720)
        server.start_camera("1")
        
        # In Tornado handler:
        async for frame in server.get_frame_generator("1"):
            yield frame
    """
    
    # Placeholder frame for when camera is not available
    PLACEHOLDER_FRAME = None
    
    def __init__(self):
        self._cameras: Dict[str, CameraStream] = {}
        self._capture_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}
        self._global_lock = threading.Lock()
        
        # Generate placeholder frame
        self._generate_placeholder()
    
    def _generate_placeholder(self) -> None:
        """Generate a placeholder frame for unavailable cameras."""
        if not OPENCV_AVAILABLE:
            # Minimal 1x1 black JPEG
            self.PLACEHOLDER_FRAME = bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
                0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
                0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
                0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
                0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
                0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
                0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
                0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
                0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
                0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
                0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
                0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
                0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
                0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
                0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
                0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
                0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
                0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
                0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
                0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
                0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
                0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
                0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
                0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
                0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xF1, 0x45, 0x00,
                0x14, 0x50, 0x01, 0x45, 0x00, 0xFF, 0xD9
            ])
            return
        
        try:
            import numpy as np
            # Create a dark gray image with "No Signal" text
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            img[:] = (40, 40, 40)  # Dark gray background
            
            # Add text
            font = cv2.FONT_HERSHEY_SIMPLEX
            text = "No Signal"
            text_size = cv2.getTextSize(text, font, 1.5, 2)[0]
            text_x = (640 - text_size[0]) // 2
            text_y = (480 + text_size[1]) // 2
            cv2.putText(img, text, (text_x, text_y), font, 1.5, (100, 100, 100), 2)
            
            # Encode to JPEG
            _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            self.PLACEHOLDER_FRAME = buffer.tobytes()
        except Exception as e:
            logger.error("Failed to generate placeholder frame: %s", e)
            self.PLACEHOLDER_FRAME = b''
    
    def _start_http_server(self, camera: CameraStream, retries: int = 5) -> bool:
        """Start dedicated HTTP server for a camera's MJPEG stream.
        
        Args:
            camera: The camera stream to start HTTP server for.
            retries: Number of retries if port is busy.
            
        Returns:
            True if server started successfully.
        """
        if camera._http_server is not None:
            logger.warning("HTTP server already running for camera %s, stopping first", camera.camera_id)
            self._stop_http_server(camera)
            time.sleep(0.5)  # Wait for port to be released
        
        for attempt in range(retries):
            try:
                # Create handler class with reference to this camera
                handler_class = create_mjpeg_handler(camera)
                
                # Create HTTP server on the configured port
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(("0.0.0.0", camera.mjpeg_port))
                server_socket.listen(5)
                
                camera._http_server = HTTPServer(("0.0.0.0", camera.mjpeg_port), handler_class, bind_and_activate=False)
                camera._http_server.socket = server_socket
                
                # Start server in background thread
                def serve():
                    logger.info("Starting HTTP server for camera %s on port %d", 
                               camera.camera_id, camera.mjpeg_port)
                    try:
                        camera._http_server.serve_forever()
                    except Exception as e:
                        if camera._http_server is not None:  # Only log if not intentionally stopped
                            logger.error("HTTP server error for camera %s: %s", camera.camera_id, e)
                    finally:
                        logger.debug("HTTP server serve_forever ended for camera %s", camera.camera_id)
                
                camera._http_thread = threading.Thread(
                    target=serve,
                    daemon=True,
                    name=f"mjpeg-http-{camera.camera_id}"
                )
                camera._http_thread.start()
                
                logger.info("Dedicated HTTP server started for camera %s on port %d",
                           camera.camera_id, camera.mjpeg_port)
                return True
                
            except OSError as e:
                if e.errno == 98 or e.errno == 10048:  # Address already in use (Linux/Windows)
                    if attempt < retries - 1:
                        logger.warning("Port %d busy for camera %s, retrying in 1s (attempt %d/%d)", 
                                     camera.mjpeg_port, camera.camera_id, attempt + 1, retries)
                        time.sleep(1.0)
                        continue
                    logger.error("Port %d still in use for camera %s after %d retries", 
                               camera.mjpeg_port, camera.camera_id, retries)
                    camera.error = f"Port {camera.mjpeg_port} already in use"
                else:
                    logger.error("Failed to start HTTP server for camera %s: %s", 
                               camera.camera_id, e)
                    camera.error = str(e)
                return False
            except Exception as e:
                logger.error("Failed to start HTTP server for camera %s: %s", 
                            camera.camera_id, e)
                camera.error = str(e)
                return False
        
        return False  # Should not reach here
    
    def _stop_http_server(self, camera: CameraStream) -> None:
        """Stop dedicated HTTP server for a camera.
        
        Args:
            camera: The camera stream to stop HTTP server for.
        """
        if camera._http_server is not None:
            http_server = camera._http_server
            camera._http_server = None  # Clear reference immediately
            
            def shutdown_server():
                try:
                    http_server.shutdown()
                    # Close the socket explicitly to release the port
                    try:
                        http_server.socket.close()
                    except Exception:
                        pass
                    http_server.server_close()
                    logger.debug("HTTP server closed for camera %s", camera.camera_id)
                except Exception as e:
                    logger.debug("Error during HTTP server shutdown: %s", e)
            
            # Run shutdown in a separate thread to avoid blocking
            shutdown_thread = threading.Thread(target=shutdown_server, daemon=True)
            shutdown_thread.start()
            shutdown_thread.join(timeout=2.0)  # Wait max 2 seconds
            
            if shutdown_thread.is_alive():
                logger.warning("HTTP server shutdown taking too long for camera %s", camera.camera_id)
            else:
                logger.info("HTTP server stopped for camera %s", camera.camera_id)
        
        if camera._http_thread is not None:
            if camera._http_thread.is_alive():
                camera._http_thread.join(timeout=2.0)
            camera._http_thread = None

    def add_camera(
        self,
        camera_id: str,
        device_path: str,
        name: str = "Camera",
        width: int = 640,
        height: int = 480,
        stream_width: int = 0,
        stream_height: int = 0,
        fps: int = 15,
        quality: int = 80,
        mjpeg_port: int = 8081,
        overlay_left_text: str = "disabled",
        overlay_left_custom: str = "",
        overlay_right_text: str = "timestamp",
        overlay_right_custom: str = "",
        overlay_text_scale: int = 3,
        stream_auth_enabled: bool = False,
        stream_auth_verify: Optional[AuthVerifyCallback] = None
    ) -> bool:
        """Add a camera to the server.
        
        Args:
            camera_id: Unique identifier for the camera.
            device_path: Device path or index ("0", "1", "/dev/video0").
            name: Display name for the camera.
            width: Capture width (input resolution).
            height: Capture height (input resolution).
            stream_width: Output width (0 = same as capture).
            stream_height: Output height (0 = same as capture).
            fps: Target frames per second.
            quality: JPEG encoding quality (1-100).
            mjpeg_port: Dedicated HTTP port for MJPEG streaming.
            overlay_left_text: Left overlay type (disabled, camera_name, timestamp, custom, capture_info).
            overlay_left_custom: Custom text for left overlay.
            overlay_right_text: Right overlay type.
            overlay_right_custom: Custom text for right overlay.
            overlay_text_scale: Text scale (1-10).
            stream_auth_enabled: Whether HTTP Basic authentication is required.
            stream_auth_verify: Callback function to verify credentials (username, password) -> bool.
            
        Returns:
            True if camera was added successfully.
        """
        with self._global_lock:
            if camera_id in self._cameras:
                logger.warning("Camera %s already exists", camera_id)
                return False
            
            self._cameras[camera_id] = CameraStream(
                camera_id=camera_id,
                device_path=device_path,
                name=name,
                width=width,
                height=height,
                stream_width=stream_width,
                stream_height=stream_height,
                fps=fps,
                quality=quality,
                mjpeg_port=mjpeg_port,
                overlay_left_text=overlay_left_text,
                overlay_left_custom=overlay_left_custom,
                overlay_right_text=overlay_right_text,
                overlay_right_custom=overlay_right_custom,
                overlay_text_scale=overlay_text_scale,
                stream_auth_enabled=stream_auth_enabled,
                stream_auth_verify=stream_auth_verify,
            )
            logger.info("Added camera %s: %s (device=%s, capture=%dx%d, stream=%dx%d, port=%d, auth=%s)", 
                       camera_id, name, device_path, width, height,
                       stream_width or width, stream_height or height, mjpeg_port,
                       "enabled" if stream_auth_enabled else "disabled")
            return True
    
    def remove_camera(self, camera_id: str) -> bool:
        """Remove a camera from the server.
        
        Args:
            camera_id: The camera ID to remove.
            
        Returns:
            True if camera was removed.
        """
        self.stop_camera(camera_id)
        
        with self._global_lock:
            if camera_id in self._cameras:
                del self._cameras[camera_id]
                logger.info("Removed camera %s", camera_id)
                return True
            return False
    
    def update_camera(
        self,
        camera_id: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        quality: Optional[int] = None,
        overlay_left_text: Optional[str] = None,
        overlay_left_custom: Optional[str] = None,
        overlay_right_text: Optional[str] = None,
        overlay_right_custom: Optional[str] = None,
        overlay_text_scale: Optional[int] = None
    ) -> bool:
        """Update camera settings. Requires restart of the camera for size/fps changes."""
        camera = self._cameras.get(camera_id)
        if not camera:
            return False
        
        # Overlay settings can be updated without restart
        with camera._lock:
            if overlay_left_text is not None:
                camera.overlay_left_text = overlay_left_text
            if overlay_left_custom is not None:
                camera.overlay_left_custom = overlay_left_custom
            if overlay_right_text is not None:
                camera.overlay_right_text = overlay_right_text
            if overlay_right_custom is not None:
                camera.overlay_right_custom = overlay_right_custom
            if overlay_text_scale is not None:
                camera.overlay_text_scale = max(1, min(10, overlay_text_scale))
        
        # Check if we need to restart camera (size/fps/quality changes)
        needs_restart = any([
            width is not None and width != camera.width,
            height is not None and height != camera.height,
            fps is not None and fps != camera.fps,
            quality is not None and quality != camera.quality
        ])
        
        if needs_restart:
            was_running = camera.is_running
            if was_running:
                self.stop_camera(camera_id)
            
            with camera._lock:
                if width is not None:
                    camera.width = width
                if height is not None:
                    camera.height = height
                if fps is not None:
                    camera.fps = fps
                if quality is not None:
                    camera.quality = max(1, min(100, quality))
            
            if was_running:
                self.start_camera(camera_id)
        
        return True
    
    def start_camera(self, camera_id: str) -> bool:
        """Start capturing from a camera.
        
        Args:
            camera_id: The camera ID to start.
            
        Returns:
            True if camera was started successfully.
        """
        if not OPENCV_AVAILABLE:
            logger.error("Cannot start camera: OpenCV not available")
            return False
        
        camera = self._cameras.get(camera_id)
        if not camera:
            logger.error("Camera %s not found", camera_id)
            return False
        
        if camera.is_running:
            logger.warning("Camera %s is already running", camera_id)
            return True
        
        # Start dedicated HTTP server for this camera's stream
        if not self._start_http_server(camera):
            logger.error("Failed to start HTTP server for camera %s", camera_id)
            # Continue anyway - capture will work, just no dedicated stream
        
        # Create stop event
        stop_event = threading.Event()
        self._stop_events[camera_id] = stop_event
        
        # Start capture thread
        thread = threading.Thread(
            target=self._capture_loop,
            args=(camera, stop_event),
            daemon=True,
            name=f"mjpeg-capture-{camera_id}"
        )
        self._capture_threads[camera_id] = thread
        thread.start()
        
        logger.info("Started camera %s (MJPEG on port %d)", camera_id, camera.mjpeg_port)
        return True
    
    def stop_camera(self, camera_id: str) -> bool:
        """Stop capturing from a camera.
        
        Args:
            camera_id: The camera ID to stop.
            
        Returns:
            True if camera was stopped.
        """
        camera = self._cameras.get(camera_id)
        
        # Stop HTTP server first (so clients get disconnected cleanly)
        if camera:
            self._stop_http_server(camera)
        
        stop_event = self._stop_events.get(camera_id)
        if stop_event:
            stop_event.set()
        
        thread = self._capture_threads.get(camera_id)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        
        # Clean up
        self._stop_events.pop(camera_id, None)
        self._capture_threads.pop(camera_id, None)
        
        if camera:
            camera.is_running = False
            camera.error = None
        
        logger.info("Stopped camera %s", camera_id)
        return True
    
    def stop_all(self) -> None:
        """Stop all cameras."""
        for camera_id in list(self._cameras.keys()):
            self.stop_camera(camera_id)
    
    def _get_overlay_text(self, camera: CameraStream, overlay_type: str, custom_text: str) -> str:
        """Generate overlay text based on type.
        
        Args:
            camera: The camera stream.
            overlay_type: Type of overlay (camera_name, timestamp, custom, capture_info, disabled).
            custom_text: Custom text if type is 'custom'.
            
        Returns:
            The text to display, or empty string if disabled.
        """
        if overlay_type == "disabled":
            return ""
        elif overlay_type == "camera_name":
            return camera.name
        elif overlay_type == "timestamp":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif overlay_type == "custom":
            return custom_text
        elif overlay_type == "capture_info":
            return f"{camera.width}x{camera.height} @ {camera._real_fps:.1f}fps"
        return ""
    
    def _draw_overlay(self, frame, camera: CameraStream) -> None:
        """Draw text overlay on frame (in-place modification).
        
        Args:
            frame: OpenCV frame (numpy array) to draw on.
            camera: Camera stream with overlay settings.
        """
        left_text = self._get_overlay_text(camera, camera.overlay_left_text, camera.overlay_left_custom)
        right_text = self._get_overlay_text(camera, camera.overlay_right_text, camera.overlay_right_custom)
        
        if not left_text and not right_text:
            return
        
        # Get actual frame dimensions from the frame itself, not camera config
        frame_height, frame_width = frame.shape[:2]
        
        # Calculate font scale based on image size and text scale setting
        # Base scale is relative to 720p, text_scale is 1-10
        base_scale = frame_height / 720.0
        font_scale = base_scale * (camera.overlay_text_scale / 5.0)  # Scale 5 = base size
        font_scale = max(0.3, min(3.0, font_scale))  # Clamp to reasonable range
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = max(1, int(font_scale * 2))
        
        # Padding from edges
        padding = max(5, int(10 * base_scale))
        
        # Calculate Y position (bottom of frame with padding)
        # Text baseline is at y_pos, so we need space for descenders
        text_height = cv2.getTextSize("Ay", font, font_scale, thickness)[0][1]
        y_pos = frame_height - padding - 4
        
        # Draw left text
        if left_text:
            text_size = cv2.getTextSize(left_text, font, font_scale, thickness)[0]
            x_pos = padding
            
            # Ensure text fits within frame
            if x_pos + text_size[0] > frame_width - padding:
                # Truncate text if too long
                while len(left_text) > 3 and cv2.getTextSize(left_text + "...", font, font_scale, thickness)[0][0] > frame_width // 2:
                    left_text = left_text[:-1]
                left_text += "..."
                text_size = cv2.getTextSize(left_text, font, font_scale, thickness)[0]
            
            # Draw background rectangle for readability
            bg_rect_start = (max(0, x_pos - 2), max(0, y_pos - text_size[1] - 2))
            bg_rect_end = (min(frame_width, x_pos + text_size[0] + 2), min(frame_height, y_pos + 4))
            cv2.rectangle(frame, bg_rect_start, bg_rect_end, (0, 0, 0), -1)
            
            # Draw text
            cv2.putText(frame, left_text, (x_pos, y_pos), font, font_scale, (255, 255, 255), thickness)
        
        # Draw right text
        if right_text:
            text_size = cv2.getTextSize(right_text, font, font_scale, thickness)[0]
            x_pos = frame_width - text_size[0] - padding
            
            # Ensure x_pos is not negative
            x_pos = max(padding, x_pos)
            
            # Draw background rectangle for readability
            bg_rect_start = (max(0, x_pos - 2), max(0, y_pos - text_size[1] - 2))
            bg_rect_end = (min(frame_width, x_pos + text_size[0] + 2), min(frame_height, y_pos + 4))
            cv2.rectangle(frame, bg_rect_start, bg_rect_end, (0, 0, 0), -1)
            
            # Draw text
            cv2.putText(frame, right_text, (x_pos, y_pos), font, font_scale, (255, 255, 255), thickness)
    
    def _capture_loop(self, camera: CameraStream, stop_event: threading.Event) -> None:
        """Main capture loop running in a separate thread."""
        camera.is_running = True
        camera.error = None
        frame_interval = 1.0 / camera.fps
        
        # Parse device path
        try:
            device_index = int(camera.device_path)
        except ValueError:
            device_index = camera.device_path
        
        # Open capture device
        try:
            if isinstance(device_index, int):
                # Windows: use DirectShow backend
                cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(device_index)
            
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open camera device: {camera.device_path}")
            
            # Configure capture
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera.height)
            cap.set(cv2.CAP_PROP_FPS, camera.fps)
            
            # Some cameras need a buffer size reduction for lower latency
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            camera.capture = cap
            logger.info("Camera %s opened: %dx%d @ %d fps",
                       camera.camera_id,
                       int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                       int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                       int(cap.get(cv2.CAP_PROP_FPS)))
        
        except Exception as e:
            camera.error = str(e)
            camera.is_running = False
            logger.error("Failed to open camera %s: %s", camera.camera_id, e)
            return
        
        # Capture loop
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, camera.quality]
        
        # Determine output resolution
        output_width = camera.stream_width if camera.stream_width > 0 else camera.width
        output_height = camera.stream_height if camera.stream_height > 0 else camera.height
        need_resize = (output_width != camera.width or output_height != camera.height)
        
        if need_resize:
            logger.info("Camera %s: will resize from %dx%d to %dx%d",
                       camera.camera_id, camera.width, camera.height, output_width, output_height)
        
        while not stop_event.is_set():
            loop_start = time.monotonic()
            
            try:
                ret, frame = cap.read()
                
                if not ret:
                    camera.error = "Failed to read frame"
                    logger.warning("Camera %s: failed to read frame", camera.camera_id)
                    time.sleep(0.1)
                    continue
                
                # Resize frame if output resolution differs from capture resolution
                if need_resize:
                    frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_LINEAR)
                
                # Apply text overlay if configured (on resized frame)
                self._draw_overlay(frame, camera)
                
                # Encode to JPEG
                _, buffer = cv2.imencode('.jpg', frame, encode_params)
                jpeg_bytes = buffer.tobytes()
                
                # Update camera state
                current_time = time.time()
                frame_size = len(jpeg_bytes)
                with camera._lock:
                    camera.last_frame = jpeg_bytes
                    camera.last_frame_time = current_time
                    camera.last_frame_size = frame_size
                    camera.frame_count += 1
                    camera.error = None
                    
                    # Update real-time stats (reset every second)
                    camera._stats_frame_count += 1
                    camera._stats_bytes_sent += frame_size
                    elapsed = current_time - camera._stats_start_time
                    if elapsed >= 1.0:
                        camera._real_fps = camera._stats_frame_count / elapsed
                        camera._bandwidth_kbps = (camera._stats_bytes_sent * 8) / (elapsed * 1000)
                        camera._stats_start_time = current_time
                        camera._stats_frame_count = 0
                        camera._stats_bytes_sent = 0
                
                # Notify subscribers
                for subscriber_queue in camera.subscribers[:]:
                    try:
                        # Non-blocking put, drop old frames if queue is full
                        if subscriber_queue.full():
                            try:
                                subscriber_queue.get_nowait()
                            except Empty:
                                pass
                        subscriber_queue.put_nowait(jpeg_bytes)
                    except Exception:
                        pass
            
            except Exception as e:
                camera.error = str(e)
                logger.error("Camera %s capture error: %s", camera.camera_id, e)
            
            # Frame rate control
            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        # Cleanup
        cap.release()
        camera.capture = None
        camera.is_running = False
        logger.info("Camera %s capture loop ended", camera.camera_id)
    
    def get_frame(self, camera_id: str) -> Optional[bytes]:
        """Get the latest frame from a camera.
        
        Args:
            camera_id: The camera ID.
            
        Returns:
            JPEG bytes or None if not available.
        """
        camera = self._cameras.get(camera_id)
        if not camera:
            return self.PLACEHOLDER_FRAME
        
        with camera._lock:
            if camera.last_frame:
                return camera.last_frame
        
        return self.PLACEHOLDER_FRAME
    
    def subscribe(self, camera_id: str) -> Optional[Queue]:
        """Subscribe to a camera's frame stream.
        
        Args:
            camera_id: The camera ID.
            
        Returns:
            A Queue that will receive frames, or None if camera doesn't exist.
        """
        camera = self._cameras.get(camera_id)
        if not camera:
            return None
        
        # Create a queue with limited size to prevent memory issues
        queue = Queue(maxsize=2)
        camera.subscribers.append(queue)
        return queue
    
    def unsubscribe(self, camera_id: str, queue: Queue) -> None:
        """Unsubscribe from a camera's frame stream."""
        camera = self._cameras.get(camera_id)
        if camera and queue in camera.subscribers:
            camera.subscribers.remove(queue)
    
    async def frame_generator(self, camera_id: str) -> AsyncGenerator[bytes, None]:
        """Async generator that yields MJPEG frames.
        
        Usage in Tornado handler:
            async for frame in server.frame_generator(camera_id):
                self.write(frame)
                await self.flush()
        """
        camera = self._cameras.get(camera_id)
        if not camera:
            # Yield placeholder once
            yield self._format_mjpeg_frame(self.PLACEHOLDER_FRAME)
            return
        
        queue = self.subscribe(camera_id)
        if not queue:
            yield self._format_mjpeg_frame(self.PLACEHOLDER_FRAME)
            return
        
        try:
            while True:
                try:
                    # Wait for frame with timeout
                    frame = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: queue.get(timeout=1.0)
                    )
                    yield self._format_mjpeg_frame(frame)
                except Empty:
                    # Send placeholder on timeout
                    yield self._format_mjpeg_frame(self.PLACEHOLDER_FRAME)
        finally:
            self.unsubscribe(camera_id, queue)
    
    def _format_mjpeg_frame(self, frame_data: bytes) -> bytes:
        """Format a frame for MJPEG streaming."""
        return (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame_data)).encode() + b"\r\n"
            b"\r\n" + frame_data + b"\r\n"
        )
    
    def get_camera_status(self, camera_id: str) -> Dict:
        """Get the status of a camera."""
        camera = self._cameras.get(camera_id)
        if not camera:
            return {"exists": False}
        
        # Calculate actual output dimensions
        output_width = camera.stream_width if camera.stream_width > 0 else camera.width
        output_height = camera.stream_height if camera.stream_height > 0 else camera.height
        
        return {
            "exists": True,
            "camera_id": camera.camera_id,
            "name": camera.name,
            "device_path": camera.device_path,
            "is_running": camera.is_running,
            "width": output_width,
            "height": output_height,
            "capture_width": camera.width,
            "capture_height": camera.height,
            "fps": camera.fps,
            "real_fps": round(camera._real_fps, 1),
            "quality": camera.quality,
            "mjpeg_port": camera.mjpeg_port,
            "frame_count": camera.frame_count,
            "last_frame_time": camera.last_frame_time,
            "last_frame_size": camera.last_frame_size,
            "bandwidth_kbps": round(camera._bandwidth_kbps, 1),
            "error": camera.error,
            "subscriber_count": len(camera.subscribers),
        }
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all cameras."""
        return {
            camera_id: self.get_camera_status(camera_id)
            for camera_id in self._cameras.keys()
        }
    
    def detect_camera_capabilities(self, device_path: str) -> Dict:
        """Detect the capabilities of a camera device.
        
        Args:
            device_path: Device path or index ("0", "1", "/dev/video0").
            
        Returns:
            Dictionary with detected capabilities:
            - supported_resolutions: List of detected resolutions
            - current_resolution: Current camera resolution
            - max_fps: Maximum FPS capability
            - backend: Video capture backend name
            - error: Error message if detection failed
        """
        import platform
        import subprocess
        
        result = {
            "supported_resolutions": [],
            "current_resolution": None,
            "max_fps": 30,
            "backend": "unknown",
            "error": None
        }
        
        # On Linux, try v4l2-ctl first (works even if device is busy)
        is_linux = platform.system().lower() == "linux"
        is_v4l2_device = device_path.startswith("/dev/video") or (is_linux and device_path.isdigit())
        
        if is_linux and is_v4l2_device:
            # Convert numeric device to /dev/videoN format
            if device_path.isdigit():
                device_path_v4l2 = f"/dev/video{device_path}"
            else:
                device_path_v4l2 = device_path
            
            v4l2_result = self._detect_v4l2_resolutions(device_path_v4l2)
            if v4l2_result["supported_resolutions"]:
                return v4l2_result
            # If v4l2-ctl failed but no error, device might be busy - return partial result
            if not v4l2_result.get("error"):
                logger.debug("V4L2 detection returned no resolutions for %s", device_path)
        
        if not OPENCV_AVAILABLE:
            result["error"] = "OpenCV not available"
            return result
        
        try:
            # Parse device path
            try:
                device_index = int(device_path)
            except ValueError:
                device_index = device_path
            
            # Open capture device
            if isinstance(device_index, int):
                # Windows: use DirectShow backend
                cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
                result["backend"] = "DirectShow"
            else:
                cap = cv2.VideoCapture(device_index)
                result["backend"] = "V4L2" if "video" in str(device_index) else "default"
            
            if not cap.isOpened():
                result["error"] = f"Cannot open camera device: {device_path}"
                return result
            
            # Get current resolution
            current_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            current_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            result["current_resolution"] = f"{current_width}x{current_height}"
            result["max_fps"] = int(cap.get(cv2.CAP_PROP_FPS)) or 30
            
            # Common resolutions to test
            test_resolutions = [
                (320, 240),    # QVGA
                (352, 288),    # CIF
                (640, 360),    # nHD
                (640, 480),    # VGA
                (800, 600),    # SVGA
                (960, 540),    # qHD
                (1024, 576),   # WSVGA
                (1024, 768),   # XGA
                (1280, 720),   # HD 720p
                (1280, 960),   # SXGA-
                (1280, 1024),  # SXGA
                (1600, 900),   # HD+
                (1920, 1080),  # Full HD 1080p
                (2560, 1440),  # QHD
                (3840, 2160),  # 4K UHD
            ]
            
            supported = []
            for width, height in test_resolutions:
                # Try to set resolution
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                
                # Check if it was accepted
                actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                resolution = f"{actual_width}x{actual_height}"
                if resolution not in supported and actual_width > 0 and actual_height > 0:
                    supported.append(resolution)
            
            # Sort by resolution (ascending)
            def res_key(res):
                w, h = map(int, res.split('x'))
                return w * h
            
            result["supported_resolutions"] = sorted(set(supported), key=res_key)
            
            cap.release()
            logger.info("Detected camera capabilities for %s: %s", 
                       device_path, result["supported_resolutions"])
            
        except Exception as e:
            result["error"] = str(e)
            logger.error("Failed to detect camera capabilities for %s: %s", device_path, e)
        
        return result
    
    def _detect_v4l2_resolutions(self, device_path: str) -> Dict:
        """Detect resolutions using v4l2-ctl (Linux only).
        
        This method works even when the camera device is busy/in use.
        
        Args:
            device_path: Device path (e.g., /dev/video0).
            
        Returns:
            Dictionary with detected capabilities.
        """
        import subprocess
        import re
        
        result = {
            "supported_resolutions": [],
            "current_resolution": None,
            "max_fps": 30,
            "backend": "V4L2",
            "error": None
        }
        
        try:
            # Get supported frame sizes for MJPEG and YUYV formats
            cmd_result = subprocess.run(
                ["v4l2-ctl", "-d", device_path, "--list-framesizes=mjpeg"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = cmd_result.stdout
            
            # If MJPEG not available, try YUYV
            if not output.strip() or cmd_result.returncode != 0:
                cmd_result = subprocess.run(
                    ["v4l2-ctl", "-d", device_path, "--list-framesizes=yuyv"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                output = cmd_result.stdout
            
            # Parse discrete sizes: "Size: Discrete 640x480"
            discrete_pattern = r'Size:\s+Discrete\s+(\d+)x(\d+)'
            resolutions = []
            
            for match in re.finditer(discrete_pattern, output):
                width, height = int(match.group(1)), int(match.group(2))
                res = f"{width}x{height}"
                if res not in resolutions:
                    resolutions.append(res)
            
            # Parse stepwise sizes if no discrete sizes found
            # "Size: Stepwise 160x120 - 1920x1080 with step 8/8"
            if not resolutions:
                stepwise_pattern = r'Size:\s+Stepwise\s+(\d+)x(\d+)\s+-\s+(\d+)x(\d+)'
                match = re.search(stepwise_pattern, output)
                if match:
                    min_w, min_h = int(match.group(1)), int(match.group(2))
                    max_w, max_h = int(match.group(3)), int(match.group(4))
                    
                    # Add common resolutions within the range
                    common = [
                        (320, 240), (640, 480), (800, 600),
                        (1024, 768), (1280, 720), (1280, 960),
                        (1920, 1080), (2560, 1440), (3840, 2160)
                    ]
                    for w, h in common:
                        if min_w <= w <= max_w and min_h <= h <= max_h:
                            resolutions.append(f"{w}x{h}")
            
            if resolutions:
                # Sort by resolution
                def res_key(res):
                    w, h = map(int, res.split('x'))
                    return w * h
                
                result["supported_resolutions"] = sorted(resolutions, key=res_key)
                logger.info("V4L2 detected resolutions for %s: %s", 
                           device_path, result["supported_resolutions"])
            
        except FileNotFoundError:
            logger.debug("v4l2-ctl not found")
            result["error"] = "v4l2-ctl not installed"
        except subprocess.TimeoutExpired:
            logger.warning("v4l2-ctl timed out for %s", device_path)
            result["error"] = "v4l2-ctl timed out"
        except Exception as e:
            logger.debug("V4L2 resolution detection failed for %s: %s", device_path, e)
            result["error"] = str(e)
        
        return result


# Global MJPEG server instance
_mjpeg_server: Optional[MJPEGServer] = None


def get_mjpeg_server() -> MJPEGServer:
    """Get the global MJPEG server instance."""
    global _mjpeg_server
    if _mjpeg_server is None:
        _mjpeg_server = MJPEGServer()
    return _mjpeg_server


def is_opencv_available() -> bool:
    """Check if OpenCV is available."""
    return OPENCV_AVAILABLE
