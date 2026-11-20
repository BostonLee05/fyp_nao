"""
integrated_monitoring.py

Camera and streaming wrapper for the NAO robot.
This module does not contain AI logic.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

try:
    import cv2
except ImportError:  # pragma: no cover - environment dependent
    cv2 = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment dependent
    np = None

from config import CAMERA_FPS, CAMERA_ID, ROBOT_IP, ROBOT_PORT
from nao_api import get_nao_manager


FrameProcessor = Callable[[np.ndarray], Optional[np.ndarray]]


class IntegratedMonitoring:
    def __init__(
        self,
        robot_ip: str = ROBOT_IP,
        robot_port: int = ROBOT_PORT,
        camera_id: int = CAMERA_ID,
        camera_fps: int = CAMERA_FPS,
        resolution: int = 2,
        color_space: int = 11,
    ):
        self.robot_ip = robot_ip
        self.robot_port = robot_port
        self.camera_id = camera_id
        self.camera_fps = camera_fps
        self.resolution = resolution
        self.color_space = color_space

        self._api = get_nao_manager()
        self._video = None
        self._client_name = None

        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._frame_processor: Optional[FrameProcessor] = None

        self._raw_frame = None
        self._current_frame = None
        self._current_jpeg = None
        self._processed_frame = None
        self._ai_processing = False
        self._ai_thread = None
        self._last_ai_submit = 0.0
        self._preview_submit_interval = 1.0 / 12.0
        self._status = {
            "running": False,
            "connected": False,
            "camera_ready": False,
            "camera_id": self.camera_id,
            "fps": 0.0,
            "frame_count": 0,
            "width": None,
            "height": None,
            "last_error": None,
        }

    def set_frame_processor(self, processor: Optional[FrameProcessor]) -> None:
        with self._lock:
            self._frame_processor = processor

    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            if cv2 is None or np is None:
                raise RuntimeError(
                    "OpenCV and NumPy are required for vision streaming."
                )

            if not self._api.is_connected():
                self._api.connect(self.robot_ip, self.robot_port)

            self._video = self._api.get_service("ALVideoDevice")
            self._client_name = self._video.subscribeCamera(
                "WebVisionStream",
                self.camera_id,
                self.resolution,
                self.color_space,
                self.camera_fps,
            )

            self._running = True
            self._status["running"] = True
            self._status["connected"] = True
            self._status["camera_ready"] = True
            self._status["last_error"] = None
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        thread = None

        with self._lock:
            self._running = False
            self._status["running"] = False
            thread = self._thread

        if thread is not None:
            thread.join(timeout=3)

        with self._lock:
            self._unsubscribe_camera()
            self._raw_frame = None
            self._current_frame = None
            self._current_jpeg = None
            self._processed_frame = None
            self._status["camera_ready"] = False

    def _run_ai_processor(self, processor, frame):
        try:
            processed = processor(frame)
            if processed is not None:
                with self._lock:
                    self._processed_frame = processed.copy()
        except Exception as exc:
            with self._lock:
                self._status["last_error"] = str(exc)
        finally:
            with self._lock:
                self._ai_processing = False

    def _unsubscribe_camera(self) -> None:
        if self._video is not None and self._client_name is not None:
            try:
                self._video.unsubscribe(self._client_name)
            except Exception:
                pass

        self._client_name = None
        self._video = None

    def _loop(self) -> None:
        last_tick = time.time()
        frame_count = 0
        latest_error = None
        connection_lost = False

        while True:
            with self._lock:
                if not self._running:
                    break
                video = self._video
                client_name = self._client_name
                processor = self._frame_processor

            if video is None or client_name is None:
                latest_error = "Camera is not ready."
                time.sleep(0.1)
                continue

            try:
                image = video.getImageRemote(client_name)
                if image is None:
                    time.sleep(0.01)
                    continue

                width = int(image[0])
                height = int(image[1])
                image_data = image[6]

                frame = np.frombuffer(image_data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )

                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                with self._lock:
                    self._raw_frame = frame

                display_frame = frame

                if (
                    processor is not None
                    and not self._ai_processing
                    and time.time() - self._last_ai_submit
                    >= self._preview_submit_interval
                ):
                    self._ai_processing = True
                    self._last_ai_submit = time.time()
                    ai_thread = threading.Thread(
                        target=self._run_ai_processor,
                        args=(processor, frame.copy()),
                        daemon=True,
                        name="VisionAIProcessor",
                    )
                    ai_thread.start()

                with self._lock:
                    if self._processed_frame is not None:
                        display_frame = self._processed_frame

                ok, jpeg = cv2.imencode(
                    ".jpg",
                    display_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 70],
                )

                if ok:
                    with self._lock:
                        self._current_jpeg = jpeg.tobytes()
                        self._current_frame = display_frame.copy()

                frame_count += 1
                now = time.time()
                elapsed = max(now - last_tick, 1e-6)

                with self._lock:
                    self._status["fps"] = frame_count / elapsed
                    self._status["frame_count"] = frame_count
                    self._status["width"] = width
                    self._status["height"] = height
                    self._status["connected"] = True
                    self._status["camera_ready"] = True
                    self._status["last_error"] = None

            except Exception as exc:
                latest_error = str(exc)
                connection_lost = not self._api.is_connected()

                with self._lock:
                    self._status["last_error"] = latest_error

                if connection_lost:
                    print(
                        "[Monitor] NAO connection lost; stopping camera stream: "
                        f"{latest_error}"
                    )
                    with self._lock:
                        self._running = False
                    break

                print(f"[Monitor] ERROR: {latest_error}")
                time.sleep(0.1)

        with self._lock:
            if latest_error is not None:
                self._status["last_error"] = latest_error
            self._status["running"] = False
            self._status["camera_ready"] = False
            if connection_lost:
                self._status["connected"] = False
            self._unsubscribe_camera()

    def get_frame(self):
        with self._lock:
            if self._current_frame is None:
                return None
            return self._current_frame.copy()

    def get_jpeg(self):
        with self._lock:
            return self._current_jpeg

    def get_status(self):
        with self._lock:
            return dict(self._status)

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def mjpeg_stream(self):
        last_sent = 0.0
        while True:
            if not self.is_running():
                time.sleep(0.1)
                continue

            jpeg = self.get_jpeg()
            if jpeg is None:
                time.sleep(0.02)
                continue

            now = time.time()
            if now - last_sent < 1.0 / 12.0:
                time.sleep(0.01)
                continue
            last_sent = now

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                jpeg +
                b"\r\n"
            )


monitor = IntegratedMonitoring()
