"""
modules/face_registration.py

NAO-camera face registration.

Captures a small set of face images from the NAO camera and stores
them in dataset/<student_id>/ for the existing VisionSystem to use.

The module deliberately uses the shared qi.Session supplied by
NAOManager. It does not create another robot connection.
"""

import os
import threading
import time
from typing import Callable, Optional

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    from insightface.app import FaceAnalysis
except ImportError:
    FaceAnalysis = None

class FaceRegistration:
    DIRECTIONS = [
        ("front", "Please look straight at me."),
        ("left", "Please slowly turn your head to the left."),
        ("right", "Please slowly turn your head to the right."),
        ("up", "Please look slightly up."),
        ("down", "Please look slightly down."),
    ]
    PHOTOS_PER_DIRECTION = 3

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._cancel_requested = False

        self._student_id = None
        self._folder = None
        self._current_direction = None
        self._captured = 0
        self._capture_event = 0
        self._total = (
                len(self.DIRECTIONS)
                * self.PHOTOS_PER_DIRECTION
        )
        self._message = "Ready."
        self._error = None
        self._completed = False
        self._cancelled = False

        self._face_analyzer = None

    def is_running(self):
        with self._lock:
            return self._running

    def get_status(self, student_id=None):
        with self._lock:
            same_student = (
                student_id is None
                or self._student_id == student_id
            )

            if not same_student:
                return {
                    "running": False,
                    "student_id": self._student_id,
                    "current_direction": None,
                    "captured": 0,
                    "capture_event": 0,
                    "total": self._total,
                    "message": "Ready.",
                    "error": None,
                    "completed": False,
                    "cancelled": False,
                }

            return {
                "running": self._running and same_student,
                "student_id": self._student_id,
                "current_direction": self._current_direction,
                "captured": self._captured,
                "capture_event": self._capture_event,
                "total": self._total,
                "message": self._message,
                "error": self._error,
                "completed": self._completed and same_student,
                "cancelled": self._cancelled,
            }

    def start(
        self,
        session,
        speaker=None,
        student_id="",
        dataset_folder="",
        on_complete: Optional[Callable[[str], None]] = None
    ):
        if cv2 is None or np is None:
            raise RuntimeError(
                "OpenCV and NumPy are required for face registration."
            )

        with self._lock:
            if self._running:
                return False

            self._running = True
            self._cancel_requested = False
            self._student_id = student_id
            self._folder = dataset_folder
            self._current_direction = None
            self._captured = 0
            self._capture_event = 0
            self._message = "Starting camera..."
            self._error = None
            self._completed = False
            self._cancelled = False

        os.makedirs(dataset_folder, exist_ok=True)

        thread = threading.Thread(
            target=self._run,
            args=(session, speaker, on_complete),
            daemon=True,
            name=f"FaceRegistration-{student_id}"
        )
        thread.start()

        return True

    def cancel(self):
        with self._lock:
            self._cancel_requested = True
            self._message = "Cancelling registration..."
            self._cancelled = True

    def _set_status(self, **values):
        with self._lock:
            for key, value in values.items():
                setattr(self, key, value)

    def _is_cancelled(self):
        with self._lock:
            return self._cancel_requested

    @staticmethod
    def _speak(speaker, session, text):
        if speaker is not None:
            speaker.speak(text)
            return

        # Fallback: use ALTextToSpeech directly if a Speaker instance
        # was not supplied by the route.
        session.service("ALTextToSpeech").say(text)

    @staticmethod
    def _detect_face(frame_bgr):
        if cv2 is None:
            return False

        gray = cv2.cvtColor(
            frame_bgr,
            cv2.COLOR_BGR2GRAY
        )

        cascade = cv2.CascadeClassifier(
            os.path.join(
                cv2.data.haarcascades,
                "haarcascade_frontalface_default.xml"
            )
        )

        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60)
        )

        return len(faces) > 0

    @staticmethod
    def _image_to_bgr(image):
        # NAOqi ALVideoDevice image structure:
        # [width, height, layers, colorSpace, time, time, data, ...]
        width = int(image[0])
        height = int(image[1])
        raw = image[6]

        frame_rgb = np.frombuffer(
            raw,
            dtype=np.uint8
        ).reshape(
            (height, width, 3)
        )

        return cv2.cvtColor(
            frame_rgb,
            cv2.COLOR_RGB2BGR
        )

    def _get_face_landmarks(self, frame_bgr):

        if FaceAnalysis is None:
            raise RuntimeError(
                "InsightFace is required for face registration."
            )

        if self._face_analyzer is None:

            self._face_analyzer = FaceAnalysis(
                name="buffalo_l",
                providers=["CPUExecutionProvider"]
            )

            self._face_analyzer.prepare(
                ctx_id=0,
                det_size=(320, 320)
            )

        faces = self._face_analyzer.get(frame_bgr)

        if not faces:
            return None

        face = max(
            faces,
            key=lambda f: (
                f.bbox[2] - f.bbox[0]
            ) * (
                f.bbox[3] - f.bbox[1]
            )
        )

        if face.kps is None:
            return None

        return face.kps

    def _check_direction(self, landmarks, direction):

        if landmarks is None:
            return False

        left_eye = landmarks[0]
        right_eye = landmarks[1]
        nose = landmarks[2]
        left_mouth = landmarks[3]
        right_mouth = landmarks[4]

        eye_center = (
            left_eye + right_eye
        ) / 2.0

        mouth_center = (
            left_mouth + right_mouth
        ) / 2.0

        eye_distance = abs(
            right_eye[0] - left_eye[0]
        )

        if eye_distance < 10:
            return False

        horizontal_ratio = (
            (nose[0] - eye_center[0])
            / eye_distance
        )

        face_height = abs(
            mouth_center[1] - eye_center[1]
        )

        if face_height < 10:
            return False

        vertical_ratio = (
            (nose[1] - eye_center[1])
            / face_height
        )

        if direction == "front":
            return (
                abs(horizontal_ratio) < 0.12
                and
                0.30 < vertical_ratio < 0.65
            )

        if direction == "left":
            return horizontal_ratio > 0.14

        if direction == "right":
            return horizontal_ratio < -0.14

        if direction == "up":
            return vertical_ratio < 0.30

        if direction == "down":
            return vertical_ratio > 0.66

        return False

    def _capture_direction(
            self,
            video,
            client_name,
            direction,
            filename,
            speaker=None,
            session=None
    ):

        self._set_status(
            current_direction=direction,
            message=(
                f"Waiting for correct "
                f"{direction} pose..."
            )
        )

        deadline = time.time() + 30
        consecutive_correct_frames = 0
        last_retry_speech = 0.0

        while time.time() < deadline:

            if self._is_cancelled():
                return None

            image = video.getImageRemote(
                client_name
            )

            if image is None:
                time.sleep(0.2)
                continue

            try:

                frame = self._image_to_bgr(image)

                landmarks = self._get_face_landmarks(
                    frame
                )

                if landmarks is None:
                    self._set_status(
                        message=(
                            f"No face detected. "
                            f"Please show your face for "
                            f"the {direction} pose."
                        )
                    )

                    consecutive_correct_frames = 0
                    now = time.time()
                    if now - last_retry_speech >= 7:
                        try:
                            self._speak(
                                speaker=speaker,
                                session=session,
                                text=(
                                    f"I cannot detect your face. "
                                    f"Please try the {direction} "
                                    f"direction again."
                                )
                            )
                        except Exception:
                            pass
                        last_retry_speech = now

                    time.sleep(0.15)
                    continue

                correct_pose = self._check_direction(
                    landmarks,
                    direction
                )

                if not correct_pose:
                    self._set_status(
                        message=(
                            f"Face detected, but "
                            f"please follow the "
                            f"{direction} instruction."
                        )
                    )

                    consecutive_correct_frames = 0
                    now = time.time()
                    if now - last_retry_speech >= 7:
                        try:
                            self._speak(
                                speaker=speaker,
                                session=session,
                                text=(
                                    f"I cannot detect the "
                                    f"{direction} side of your face. "
                                    f"Please try again."
                                )
                            )
                        except Exception:
                            pass
                        last_retry_speech = now

                    time.sleep(0.15)
                    continue

                consecutive_correct_frames += 1

                if consecutive_correct_frames < 3:
                    self._set_status(
                        message=(
                            f"Hold the {direction} pose "
                            f"for the camera."
                        )
                    )
                    time.sleep(0.15)
                    continue

                path = os.path.join(
                    self._folder,
                    filename
                )

                if not cv2.imwrite(
                        path,
                        frame
                ):
                    raise RuntimeError(
                        f"Failed to save {path}"
                    )

                print(
                    f"[FaceRegistration] "
                    f"Correct {direction} pose. "
                    f"Saved: {path}",
                    flush=True
                )

                return path

            finally:

                try:
                    video.releaseImage(
                        client_name
                    )
                except Exception:
                    pass

            time.sleep(0.15)

        return None

    def _run(self, session, speaker, on_complete):
        video = None
        client_name = None

        try:
            print(
                "[FaceRegistration] Worker started.",
                flush=True
            )

            print(
                "[FaceRegistration] Getting ALVideoDevice...",
                flush=True
            )
            self._set_status(
                message="Connecting to the NAO camera..."
            )

            video = session.service("ALVideoDevice")

            print(
                "[FaceRegistration] ALVideoDevice obtained.",
                flush=True
            )

            print(
                "[FaceRegistration] Subscribing to NAO camera...",
                flush=True
            )
            self._set_status(
                message="Starting the NAO camera..."
            )

            client_name = video.subscribeCamera(
                "FaceRegistration",
                0,
                1,
                11,
                15
            )

            print(
                f"[FaceRegistration] Camera subscribed: {client_name}",
                flush=True
            )

            if not client_name:
                raise RuntimeError(
                    "NAO camera subscription returned no client."
                )

            self._set_status(
                current_direction="front",
                message="NAO camera connected."
            )

            print(
                "[FaceRegistration] Starting direction sequence.",
                flush=True
            )

            global_photo_index = 0

            for direction, instruction in self.DIRECTIONS:

                if self._is_cancelled():
                    self._set_status(
                        running=False,
                        message="Face registration cancelled."
                    )

                    return

                # Tell the student the direction.
                self._speak(
                    speaker,
                    session,
                    instruction
                )

                self._set_status(
                    current_direction=direction,
                    message=instruction
                )

                time.sleep(2)

                for photo_number in range(
                        1,
                        self.PHOTOS_PER_DIRECTION + 1
                ):

                    if self._is_cancelled():
                        self._set_status(
                            running=False,
                            message="Face registration cancelled."
                        )

                        return

                    global_photo_index += 1

                    filename = (
                        f"{global_photo_index:02d}_"
                        f"{direction}_{photo_number}.jpg"
                    )

                    saved = self._capture_direction(
                        video,
                        client_name,
                        direction,
                        filename,
                        speaker,
                        session
                    )

                    if saved is None:

                        if self._is_cancelled():
                            self._set_status(
                                running=False,
                                message=(
                                    "Face registration cancelled."
                                )
                            )

                            return

                        raise RuntimeError(
                            f"Correct '{direction}' "
                            "face position was not detected "
                            "within 20 seconds."
                        )

                    with self._lock:
                        self._captured += 1
                        captured = self._captured
                        self._capture_event += 1
                        capture_event = self._capture_event

                    self._set_status(
                        message=(
                            f"Captured {direction} "
                            f"photo {photo_number}/"
                            f"{self.PHOTOS_PER_DIRECTION} "
                            f"({captured}/{self._total})."
                        )
                    )

                    # Small pause between photos.
                    time.sleep(0.7)

            self._set_status(
                current_direction=None,
                message="Finalizing face registration..."
            )

            if on_complete:
                on_complete(self._folder)

            try:
                self._speak(
                    speaker,
                    session,
                    "Face registration completed successfully."
                )
            except Exception as speak_exc:
                print(
                    f"[FaceRegistration Warning] "
                    f"Could not announce completion: {speak_exc}",
                    flush=True
                )

            self._set_status(
                running=False,
                current_direction=None,
                message="Face registration completed.",
                completed=True
            )


        except Exception as exc:

            print(

                f"[FaceRegistration ERROR] "

                f"{type(exc).__name__}: {exc}",

                flush=True

            )

            try:
                self._speak(
                    speaker,
                    session,
                    "Face registration failed."
                )
            except Exception as speak_exc:
                print(
                    f"[FaceRegistration Warning] "
                    f"Could not announce failure: {speak_exc}",
                    flush=True
                )

            self._set_status(

                running=False,

                current_direction=None,

                error=f"{type(exc).__name__}: {exc}",

                message=f"Registration failed: {exc}",

                completed=False

            )

        finally:
            if video is not None and client_name is not None:
                try:
                    video.unsubscribe(
                        client_name
                    )
                except Exception:
                    pass

            with self._lock:
                self._running = False


_registration = None

def get_face_registration():
    global _registration

    if _registration is None:
        _registration = FaceRegistration()

    return _registration