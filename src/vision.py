#old version that shld be kept
import os
import time
from typing import Any, Callable, Dict, Optional

try:
    import cv2
except ImportError:  # pragma: no cover - environment dependent
    cv2 = None

try:
    import numpy as np
except ImportError:  # pragma: no cover - environment dependent
    np = None

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover - environment dependent
    YOLO = None

try:
    from insightface.app import FaceAnalysis
except ImportError:  # pragma: no cover - environment dependent
    FaceAnalysis = None

from database import (
    get_all_students,
    get_active_session,
)
from config import ATTENDANCE_COOLDOWN_SECONDS

from modules.attendance import (
    mark_attendance,
    RESULT_RECORDED,
    RESULT_ALREADY_RECORDED,
    RESULT_NO_ACTIVE_SESSION,
    RESULT_NOT_ENROLLED
)

from modules.behaviour_monitoring import (
    BehaviourTracker,
    BEHAVIOUR_FORWARD,
    BEHAVIOUR_LEFT,
    BEHAVIOUR_RIGHT,
    BEHAVIOUR_DOWN,
    BEHAVIOUR_FACE_NOT_VISIBLE,
    BEHAVIOUR_USING_PHONE,
    BEHAVIOUR_UNKNOWN
)


class VisionSystem:

    # =====================================================
    # INITIALIZE
    # =====================================================

    def __init__(
        self,
        attendance_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        behaviour_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):

        # -------------------------------
        # Camera / YOLO
        # -------------------------------

        self.CAMERA_INDEX = 0

        self.YOLO_MODEL_PATH = "yolov8n.pt"

        self.PERSON_CLASS_ID = 0
        self.CELL_PHONE_CLASS_ID = 67

        self.YOLO_CONFIDENCE = 0.50
        self.PHONE_CONFIDENCE = 0.20

        self.PHONE_PERSON_MARGIN = 40

        self.YOLO_PROCESS_EVERY_N_FRAMES = 1
        self.FACE_PROCESS_EVERY_N_FRAMES = 1

        # -------------------------------
        # Face Recognition
        # -------------------------------

        self.FACE_DETECTION_SIZE = (320, 320)

        self.FACE_SIMILARITY_THRESHOLD = 0.45
        self.CONFIRMATION_SIMILARITY_THRESHOLD = 0.45

        self.RECOGNITION_CONFIRMATIONS_REQUIRED = 2

        self.PENDING_CONFIRMATION_TIMEOUT = 6.0

        self.IDENTITY_CACHE_SECONDS = 8.0

        self.DEBUG_RECOGNITION = True

        # -------------------------------
        # Head Pose
        # -------------------------------

        self.HEAD_LEFT_THRESHOLD = -0.12
        self.HEAD_RIGHT_THRESHOLD = 0.12
        self.HEAD_DOWN_THRESHOLD = 0.58

        self.SWAP_LEFT_RIGHT = True

        # -------------------------------
        # Runtime
        # -------------------------------

        self.frame_count = 0

        self.tracked_people = {}

        self.detected_phones = []

        self.phone_assignments = {}

        self.identity_cache = {}

        self.pending_confirmations = {}

        self.attendance_attempted_tracks = set()
        self.attendance_attempt_times = {}
        self._attendance_session_id = None

        self.behaviour_tracker = BehaviourTracker()

        self.previous_time = time.time()

        self.smoothed_fps = 0.0

        self.attendance_callback = attendance_callback
        self.behaviour_callback = behaviour_callback
        self._latest_statistics = {
            "persons": 0,
            "recognized": 0,
            "unknown": 0,
            "phones": 0,
            "fps": 0.0,
            "session": None
        }

        # -------------------------------
        # AI Models (Lazy Loading)
        # -------------------------------
        self.yolo_model = None
        self.face_app = None
        self.registered_students = {}
        self._models_loaded = False

    def _ensure_models_loaded(self):

        if self._models_loaded:
            return

        self.yolo_model = self.load_yolo_model()
        self.face_app = self.load_face_model()
        self.registered_students = self.load_registered_students()

        self._models_loaded = True

    def refresh_registered_students(self):
        """Reload face embeddings without reloading the AI models."""
        if not self._models_loaded:
            return

        self.registered_students = self.load_registered_students()

    # =====================================================
    # NORMALIZE
    # =====================================================

    @staticmethod
    def normalize_embedding(embedding):

        norm = np.linalg.norm(embedding)

        if norm == 0:
            return embedding

        return embedding / norm

    # =====================================================
    # YOLO
    # =====================================================

    def load_yolo_model(self):

        if YOLO is None:
            raise RuntimeError("ultralytics is required for YOLO processing.")

        print("Loading YOLO...")

        model = YOLO(self.YOLO_MODEL_PATH)

        print("YOLO Loaded.")

        return model

    # =====================================================
    # INSIGHTFACE
    # =====================================================

    def load_face_model(self):

        if FaceAnalysis is None:
            raise RuntimeError("insightface is required for face recognition.")

        print("Loading InsightFace...")

        app = FaceAnalysis(
            name="buffalo_l",
            providers=[
                "CPUExecutionProvider"
            ]
        )

        app.prepare(
            ctx_id=0,
            det_size=self.FACE_DETECTION_SIZE
        )

        print("InsightFace Loaded.")

        return app

    # =====================================================
    # REGISTERED STUDENTS
    # =====================================================

    def load_registered_students(self):

        if cv2 is None or np is None:
            raise RuntimeError("OpenCV and NumPy are required for face registration loading.")

        students = {}
        loaded_faces = 0

        print("\nLoading registered students...")

        for student in get_all_students():

            if student["face_registered"] != 1:
                continue

            folder = student["face_folder"]

            if not folder:
                continue

            if not os.path.isdir(folder):
                continue

            embeddings = []

            for file in os.listdir(folder):

                if not file.lower().endswith(
                        (".jpg", ".jpeg", ".png")):
                    continue

                image = cv2.imread(
                    os.path.join(folder, file)
                )

                if image is None:
                    continue

                faces = self.face_app.get(image)

                if len(faces) == 0:
                    continue

                largest = max(
                    faces,
                    key=lambda f:
                    (f.bbox[2]-f.bbox[0]) *
                    (f.bbox[3]-f.bbox[1])
                )

                emb = self.normalize_embedding(
                    largest.embedding
                )

                embeddings.append(emb)

            if len(embeddings) == 0:
                print(
                    f"Skipped {student['student_id']} "
                    f"{student['student_name']} (no usable face images)"
                )
                continue

            avg = np.mean(
                embeddings,
                axis=0
            )

            avg = self.normalize_embedding(avg)

            students[
                student["student_id"]
            ] = {

                "student_id":
                    student["student_id"],

                "name":
                    student["student_name"],

                "embedding":
                    avg

            }

            print(
                f"Loaded "
                f"{student['student_id']} "
                f"{student['student_name']}"
            )
            loaded_faces += 1

        print(
            f"\nRegistered Students: "
            f"{len(students)}"
        )

        if loaded_faces == 0:
            print(
                "WARNING: No registered face embeddings were loaded. "
                "Recognition will always return Unknown until face data is available."
            )

        return students

    # =====================================================
    # FACE RECOGNITION
    # =====================================================

    def recognize_face(self, embedding):

        embedding = self.normalize_embedding(
            embedding
        )

        best_student = None

        best_similarity = -1.0

        for student in self.registered_students.values():

            similarity = float(
                np.dot(
                    embedding,
                    student["embedding"]
                )
            )

            if similarity > best_similarity:

                best_similarity = similarity

                best_student = student

        if (
                best_student is None
                or
                best_similarity <
                self.FACE_SIMILARITY_THRESHOLD
        ):

            return {

                "student_id": None,

                "name": "Unknown",

                "similarity": best_similarity

            }

        return {

            "student_id":
                best_student["student_id"],

            "name":
                best_student["name"],

            "similarity":
                best_similarity

        }

    # =====================================================
    # BOUNDING BOX HELPERS
    # =====================================================

    @staticmethod
    def get_box_center(bbox):

        x1, y1, x2, y2 = bbox

        return (
            (x1 + x2) / 2.0,
            (y1 + y2) / 2.0
        )

    @staticmethod
    def face_inside_person(face_bbox, person_bbox):

        fx1, fy1, fx2, fy2 = face_bbox
        px1, py1, px2, py2 = person_bbox

        face_center_x = (fx1 + fx2) / 2.0
        face_center_y = (fy1 + fy2) / 2.0

        return (
            px1 <= face_center_x <= px2
            and
            py1 <= face_center_y <= py2
        )

    # =====================================================
    # TRACK LOOKUP
    # =====================================================

    def find_person_for_face(self, face_bbox):

        for track_id, bbox in self.tracked_people.items():

            if self.face_inside_person(
                    face_bbox,
                    bbox):

                return track_id

        return None

    def find_person_for_phone(self, phone_bbox):

        if not self.tracked_people:
            return None

        phone_center_x, phone_center_y = (
            self.get_box_center(phone_bbox)
        )

        candidates = []

        for track_id, person_bbox in self.tracked_people.items():

            px1, py1, px2, py2 = person_bbox

            expanded_x1 = (
                px1 - self.PHONE_PERSON_MARGIN
            )

            expanded_y1 = (
                py1 - self.PHONE_PERSON_MARGIN
            )

            expanded_x2 = (
                px2 + self.PHONE_PERSON_MARGIN
            )

            expanded_y2 = (
                py2 + self.PHONE_PERSON_MARGIN
            )

            inside = (

                expanded_x1 <= phone_center_x <= expanded_x2

                and

                expanded_y1 <= phone_center_y <= expanded_y2

            )

            if not inside:
                continue

            person_center_x, person_center_y = (
                self.get_box_center(person_bbox)
            )

            distance = (

                (phone_center_x - person_center_x) ** 2

                +

                (phone_center_y - person_center_y) ** 2

            )

            candidates.append(
                (
                    distance,
                    track_id
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0]
        )

        return candidates[0][1]

    # =====================================================
    # PHONE UPDATE
    # =====================================================

    def update_phone_states(self):

        self.phone_assignments = {}

        tracks_with_phone = set()

        for phone_index, phone_bbox in enumerate(self.detected_phones):

            assigned_track = self.find_person_for_phone(phone_bbox)

            self.phone_assignments[phone_index] = assigned_track

            if assigned_track is not None:
                tracks_with_phone.add(assigned_track)

        current_time = time.time()

        for track_id in self.tracked_people.keys():

            self.behaviour_tracker.update_phone_detection(

                track_id=track_id,

                phone_detected=(
                        track_id in tracks_with_phone
                ),

                current_time=current_time

            )


    # =====================================================
    # YOLO + BYTETRACK PROCESSING
    # =====================================================

    def process_yolo(self, frame):

        self._ensure_models_loaded()

        self.frame_count += 1

        if (
                self.frame_count %
                self.YOLO_PROCESS_EVERY_N_FRAMES
                != 0
        ):
            return

        results = self.yolo_model.track(

            frame,

            persist=True,

            tracker="bytetrack.yaml",

            classes=[
                self.PERSON_CLASS_ID,
                self.CELL_PHONE_CLASS_ID
            ],

            conf=min(
                self.YOLO_CONFIDENCE,
                self.PHONE_CONFIDENCE
            ),

            imgsz=640,

            verbose=False

        )

        updated_people = {}

        updated_phones = []

        if (
                not results
                or
                results[0].boxes is None
        ):
            self.tracked_people = {}
            self.detected_phones = []

            return

        boxes_object = results[0].boxes

        boxes = (
            boxes_object.xyxy
            .cpu()
            .numpy()
            .astype(int)
        )

        class_ids = (
            boxes_object.cls
            .cpu()
            .numpy()
            .astype(int)
        )

        confidences = (
            boxes_object.conf
            .cpu()
            .numpy()
        )

        if boxes_object.id is not None:

            track_ids = (
                boxes_object.id
                .cpu()
                .numpy()
                .astype(int)
            )

        else:

            track_ids = [
                            None
                        ] * len(boxes)

        # -----------------------------------------
        # Parse detections
        # -----------------------------------------

        for (
                box,
                class_id,
                confidence,
                track_id
        ) in zip(

            boxes,
            class_ids,
            confidences,
            track_ids

        ):

            x1, y1, x2, y2 = map(
                int,
                box
            )

            # -------------------------
            # PERSON
            # -------------------------

            if class_id == self.PERSON_CLASS_ID:

                if confidence < self.YOLO_CONFIDENCE:
                    continue

                if track_id is None:
                    continue

                updated_people[
                    int(track_id)
                ] = (
                    x1,
                    y1,
                    x2,
                    y2
                )

            # -------------------------
            # PHONE
            # -------------------------

            elif class_id == self.CELL_PHONE_CLASS_ID:

                if confidence < self.PHONE_CONFIDENCE:
                    continue

                updated_phones.append(
                    (
                        x1,
                        y1,
                        x2,
                        y2
                    )
                )

        # -----------------------------------------
        # Save latest detections
        # -----------------------------------------

        self.tracked_people = updated_people

        self.detected_phones = updated_phones

        # -----------------------------------------
        # Associate phones
        # -----------------------------------------

        self.update_phone_states()

        # -----------------------------------------
        # Cleanup orphan identities
        # -----------------------------------------

        active_tracks = set(
            self.tracked_people.keys()
        )

        expired = []

        for track_id in self.identity_cache.keys():

            if track_id not in active_tracks:
                expired.append(track_id)

        for track_id in expired:
            self.identity_cache.pop(
                track_id,
                None
            )

            self.pending_confirmations.pop(
                track_id,
                None
            )

            self.attendance_attempted_tracks.discard(
                track_id
            )

        # -----------------------------------------
        # Cleanup behaviour tracker
        # -----------------------------------------

        self.behaviour_tracker.cleanup_inactive_tracks(
            active_tracks
        )

    def _emit_attendance_event(self, payload: Dict[str, Any]) -> None:
        if self.attendance_callback is None:
            return

        try:
            self.attendance_callback(payload)
        except Exception:
            pass

    def _emit_behaviour_event(self, payload: Dict[str, Any]) -> None:
        if self.behaviour_callback is None:
            return

        try:
            self.behaviour_callback(payload)
        except Exception:
            pass

    # =====================================================
    # PROCESS FACES
    # =====================================================

    def process_faces(self, frame):

        self._ensure_models_loaded()

        if (
            self.frame_count %
            self.FACE_PROCESS_EVERY_N_FRAMES
            != 0
        ):
            return

        current_time = time.time()
        detected_faces = self.face_app.get(frame)

        if self.DEBUG_RECOGNITION:
            print(
                f"[Vision] Faces detected this cycle: {len(detected_faces)}"
            )

        if len(detected_faces) == 0:
            return

        for face in detected_faces:

            face_bbox = face.bbox.astype(int)
            track_id = self.find_person_for_face(face_bbox)

            if track_id is None:
                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Face found but not matched to a tracked person: {face_bbox.tolist()}"
                    )
                continue

            detected_behaviour, _, _ = self.detect_head_behaviour(face)

            before_behaviour = self.behaviour_tracker.get_behaviour(
                track_id,
                current_time
            )

            confirmed_behaviour = self.behaviour_tracker.update_behaviour(
                track_id,
                detected_behaviour,
                current_time
            )

            if confirmed_behaviour != before_behaviour:
                self._emit_behaviour_event({
                    "track_id": track_id,
                    "behaviour": confirmed_behaviour,
                    "detected_behaviour": detected_behaviour,
                    "student_id": None,
                    "name": None,
                    "timestamp": current_time,
                })

            recognition = self.recognize_face(face.embedding)
            recognized_name = recognition["name"]
            recognized_student_id = recognition["student_id"]
            similarity = recognition["similarity"]

            if self.DEBUG_RECOGNITION:
                print(
                    f"[Vision] Track {track_id} -> {recognized_student_id} / {recognized_name} "
                    f"(similarity={similarity:.3f})"
                )

            if recognized_name == "Unknown":
                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: below face similarity threshold ({self.FACE_SIMILARITY_THRESHOLD:.2f})"
                    )
                continue

            if similarity < self.CONFIRMATION_SIMILARITY_THRESHOLD:
                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: similarity {similarity:.3f} below confirmation threshold ({self.CONFIRMATION_SIMILARITY_THRESHOLD:.2f})"
                    )
                continue

            if track_id in self.identity_cache:

                cache = self.identity_cache[track_id]

                if cache["student_id"] == recognized_student_id:
                    cache["last_seen"] = current_time
                    cache["similarity"] = max(
                        cache["similarity"],
                        similarity
                    )

                    if self.DEBUG_RECOGNITION:
                        print(
                            f"[Vision] Track {track_id}: identity cache refreshed for {recognized_student_id}"
                        )

                    self._try_mark_attendance(
                            track_id,
                            cache,
                            current_time
                    )

                continue

            if track_id not in self.pending_confirmations:
                self.pending_confirmations[track_id] = {
                    "student_id": recognized_student_id,
                    "name": recognized_name,
                    "count": 1,
                    "best_similarity": similarity,
                    "last_confirmation": current_time
                }

                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: started confirmation for {recognized_student_id}"
                    )

                continue

            pending = self.pending_confirmations[track_id]
            elapsed = (
                current_time -
                pending["last_confirmation"]
            )

            if elapsed > self.PENDING_CONFIRMATION_TIMEOUT:
                self.pending_confirmations[track_id] = {
                    "student_id": recognized_student_id,
                    "name": recognized_name,
                    "count": 1,
                    "best_similarity": similarity,
                    "last_confirmation": current_time
                }

                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: confirmation timeout reset"
                    )

                continue

            if pending["student_id"] == recognized_student_id:
                pending["count"] += 1
                pending["best_similarity"] = max(
                   pending["best_similarity"],
                   similarity
                )
                pending["last_confirmation"] = current_time

                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: confirmation {pending['count']}/{self.RECOGNITION_CONFIRMATIONS_REQUIRED} for {recognized_student_id}"
                    )

            else:
                self.pending_confirmations[track_id] = {
                    "student_id": recognized_student_id,
                    "name": recognized_name,
                    "count": 1,
                    "best_similarity": similarity,
                    "last_confirmation": current_time
                }

                if self.DEBUG_RECOGNITION:
                    print(
                        f"[Vision] Track {track_id}: switched pending identity to {recognized_student_id}"
                    )

        self.behaviour_tracker.check_face_visibility(
            self.tracked_people.keys(),
            current_time
        )

        confirmed_tracks = []

        for track_id, pending in self.pending_confirmations.items():

            if (
                pending["count"] <
                self.RECOGNITION_CONFIRMATIONS_REQUIRED
            ):
                continue

            self.identity_cache[track_id] = {
                "student_id": pending["student_id"],
                "name": pending["name"],
                "similarity": pending["best_similarity"],
                "last_seen": current_time
            }

            print("\nIDENTITY CONFIRMED")
            print(f"Track ID : {track_id}")
            print(
                f"Student  : "
                f"{pending['student_id']} - "
                f"{pending['name']}"
            )
            print(
                f"Similarity : "
                f"{pending['best_similarity']:.3f}"
            )

            self._try_mark_attendance(
                track_id,
                self.identity_cache[track_id],
                current_time
            )

            confirmed_tracks.append(track_id)

        for track_id in confirmed_tracks:
            self.pending_confirmations.pop(track_id, None)

    def _try_mark_attendance(self, track_id, identity, current_time):
        """Attempt attendance and keep retryable failures eligible."""
        active_session = get_active_session()
        session_id = (
            active_session["session_id"]
            if active_session is not None
            else None
        )

        if session_id != self._attendance_session_id:
            self.attendance_attempted_tracks.clear()
            self.attendance_attempt_times.clear()
            self._attendance_session_id = session_id

        if track_id in self.attendance_attempted_tracks:
            return

        last_attempt = self.attendance_attempt_times.get(track_id)
        if (
            last_attempt is not None
            and current_time - last_attempt < ATTENDANCE_COOLDOWN_SECONDS
        ):
            return

        attendance_result = mark_attendance(
            student_id=identity["student_id"],
            similarity=identity["similarity"],
            track_id=track_id
        )
        self.attendance_attempt_times[track_id] = current_time

        if attendance_result in (
            RESULT_RECORDED,
            RESULT_ALREADY_RECORDED
        ):
            self.attendance_attempted_tracks.add(track_id)

        if attendance_result == RESULT_RECORDED:
            print("Attendance : RECORDED")
        elif attendance_result == RESULT_ALREADY_RECORDED:
            print("Attendance : ALREADY RECORDED")
        elif attendance_result == RESULT_NO_ACTIVE_SESSION:
            print("Attendance : NO ACTIVE SESSION; will retry")
        elif attendance_result == RESULT_NOT_ENROLLED:
            print("Attendance : NOT ENROLLED; will retry")

        self._emit_attendance_event({
            "track_id": track_id,
            "student_id": identity["student_id"],
            "name": identity["name"],
            "similarity": identity["similarity"],
            "result": attendance_result,
            "timestamp": current_time,
        })

    # =====================================================
    # DETECT HEAD BEHAVIOUR
    # =====================================================

    def detect_head_behaviour(self, face):

        if face.kps is None:
            return (
                BEHAVIOUR_UNKNOWN,
                0.0,
                0.0
            )

        keypoints = face.kps

        if len(keypoints) < 5:
            return (
                BEHAVIOUR_UNKNOWN,
                0.0,
                0.0
            )

        left_eye = keypoints[0]
        right_eye = keypoints[1]
        nose = keypoints[2]
        left_mouth = keypoints[3]
        right_mouth = keypoints[4]

        eye_center_x = (
            left_eye[0] +
            right_eye[0]
        ) / 2.0

        eye_distance = abs(
            right_eye[0] -
            left_eye[0]
        )

        if eye_distance <= 0:
            return (
                BEHAVIOUR_UNKNOWN,
                0.0,
                0.0
            )

        horizontal_offset = (
            nose[0] -
            eye_center_x
        ) / eye_distance

        eye_center_y = (
            left_eye[1] +
            right_eye[1]
        ) / 2.0

        mouth_center_y = (
            left_mouth[1] +
            right_mouth[1]
        ) / 2.0

        eye_to_mouth = (
            mouth_center_y -
            eye_center_y
        )

        if eye_to_mouth <= 0:
            vertical_ratio = 0.0
        else:
            vertical_ratio = (
                nose[1] -
                eye_center_y
            ) / eye_to_mouth

        if vertical_ratio >= self.HEAD_DOWN_THRESHOLD:
            behaviour = BEHAVIOUR_DOWN
        elif horizontal_offset < self.HEAD_LEFT_THRESHOLD:
            behaviour = BEHAVIOUR_LEFT
        elif horizontal_offset > self.HEAD_RIGHT_THRESHOLD:
            behaviour = BEHAVIOUR_RIGHT
        else:
            behaviour = BEHAVIOUR_FORWARD

        if self.SWAP_LEFT_RIGHT:
            if behaviour == BEHAVIOUR_LEFT:
                behaviour = BEHAVIOUR_RIGHT
            elif behaviour == BEHAVIOUR_RIGHT:
                behaviour = BEHAVIOUR_LEFT

        return (
            behaviour,
            horizontal_offset,
            vertical_ratio
        )

    # =====================================================
    # BEHAVIOUR DISPLAY NAME
    # =====================================================

    @staticmethod
    def get_behaviour_display_name(behaviour):

        display_names = {
            BEHAVIOUR_FORWARD: "Looking Forward",
            BEHAVIOUR_LEFT: "Looking Left",
            BEHAVIOUR_RIGHT: "Looking Right",
            BEHAVIOUR_DOWN: "Looking Down",
            BEHAVIOUR_FACE_NOT_VISIBLE: "Face Not Visible",
            BEHAVIOUR_USING_PHONE: "Using Phone",
            BEHAVIOUR_UNKNOWN: "Unknown Behaviour"
        }

        return display_names.get(
            behaviour,
            behaviour
        )

    # =====================================================
    # BEHAVIOUR COLOR
    # =====================================================

    @staticmethod
    def get_behaviour_color(behaviour):

        if behaviour == BEHAVIOUR_FORWARD:
            return (0, 255, 0)

        if behaviour in (
            BEHAVIOUR_LEFT,
            BEHAVIOUR_RIGHT
        ):
            return (0, 255, 255)

        if behaviour in (
            BEHAVIOUR_DOWN,
            BEHAVIOUR_FACE_NOT_VISIBLE
        ):
            return (0, 165, 255)

        if behaviour == BEHAVIOUR_USING_PHONE:
            return (0, 0, 255)

        return (255, 255, 255)

    # =====================================================
    # DRAW PERSON
    # =====================================================

    def draw_person(
        self,
        frame,
        track_id,
        bbox
    ):

        x1, y1, x2, y2 = bbox
        current_time = time.time()

        if track_id in self.identity_cache:
            identity = self.identity_cache[track_id]
        else:
            identity = {
                "student_id": None,
                "name": "Unknown",
                "similarity": -1.0
            }

        name = identity["name"]
        student_id = identity["student_id"]
        similarity = identity["similarity"]

        behaviour = self.behaviour_tracker.get_behaviour(
            track_id,
            current_time
        )

        duration = self.behaviour_tracker.get_behaviour_duration(
            track_id,
            current_time
        )

        behaviour_name = self.get_behaviour_display_name(
            behaviour
        )

        behaviour_color = self.get_behaviour_color(
            behaviour
        )

        if name == "Unknown":
            box_color = (0, 0, 255)
        else:
            box_color = (0, 255, 0)

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            box_color,
            2
        )

        cv2.putText(
            frame,
            f"Track ID : {track_id}",
            (x1, max(y1 - 70, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            box_color,
            2
        )

        if (
            student_id is not None
            and name != "Unknown"
        ):
            identity_text = f"{student_id} - {name}"
        else:
            identity_text = "Unknown"

        cv2.putText(
            frame,
            identity_text,
            (x1, max(y1 - 45, 40)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            box_color,
            2
        )

        cv2.putText(
            frame,
            f"{behaviour_name} ({duration:.1f}s)",
            (x1, max(y1 - 20, 60)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            behaviour_color,
            2
        )

        if (
            similarity >= 0
            and name != "Unknown"
        ):
            cv2.putText(
                frame,
                f"Similarity : {similarity:.2f}",
                (x1, min(y2 + 25, frame.shape[0] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                box_color,
                2
            )

        has_phone = False

        for assigned_track in self.phone_assignments.values():
            if assigned_track == track_id:
                has_phone = True
                break

        if has_phone:
            cv2.putText(
                frame,
                "PHONE DETECTED",
                (x1, min(y2 + 50, frame.shape[0] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 0, 255),
                2
            )

    # =====================================================
    # DRAW PHONE
    # =====================================================

    def draw_phone(
        self,
        frame,
        phone_bbox,
        assigned_track_id=None
    ):

        x1, y1, x2, y2 = phone_bbox
        phone_color = (255, 0, 255)

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            phone_color,
            2
        )

        if assigned_track_id is None:
            label = "Phone"
        else:
            if assigned_track_id in self.identity_cache:
                identity = self.identity_cache[assigned_track_id]
                label = f"Phone -> {identity['name']}"
            else:
                label = f"Phone -> Track {assigned_track_id}"

        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            phone_color,
            2
        )

        center_x = int((x1 + x2) / 2)
        center_y = int((y1 + y2) / 2)

        cv2.circle(
            frame,
            (center_x, center_y),
            3,
            phone_color,
            -1
        )

    # =====================================================
    # DRAW STATISTICS
    # =====================================================

    def draw_statistics(
        self,
        frame,
        current_session=None
    ):

        current_time = time.time()
        elapsed = current_time - self.previous_time

        if elapsed > 0:
            fps = 1.0 / elapsed
        else:
            fps = 0.0

        self.previous_time = current_time

        if self.smoothed_fps == 0:
            self.smoothed_fps = fps
        else:
            self.smoothed_fps = (
                0.9 * self.smoothed_fps +
                0.1 * fps
            )

        recognized_count = len(self.identity_cache)
        total_people = len(self.tracked_people)
        unknown_count = max(0, total_people - recognized_count)
        total_phones = len(self.detected_phones)

        cv2.putText(
            frame,
            f"Persons : {total_people}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Recognized : {recognized_count}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            frame,
            f"Unknown : {unknown_count}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )

        cv2.putText(
            frame,
            f"Phones : {total_phones}",
            (10, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 0, 255),
            2
        )

        cv2.putText(
            frame,
            f"FPS : {self.smoothed_fps:.1f}",
            (10, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )

        session_summary = None

        if current_session is None:
            session_text = "Session : None"
            session_color = (0, 0, 255)

        else:
            current_session = dict(current_session)

            class_code = current_session.get("class_code", "Unknown")
            session_name = current_session.get("session_name", "Unknown")

            session_summary = {
                "class_code": class_code,
                "session_name": session_name
            }

            session_text = (
                f"Session : "
                f"{class_code} - "
                f"{session_name}"
            )

            session_color = (0, 255, 0)

        cv2.putText(
            frame,
            session_text,
            (10, 180),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            session_color,
            2
        )

        self._latest_statistics = {
            "persons": total_people,
            "recognized": recognized_count,
            "unknown": unknown_count,
            "phones": total_phones,
            "fps": round(self.smoothed_fps, 2),
            "session": session_summary if current_session is not None else None,
        }

    # =====================================================
    # DRAW EVERYTHING
    # =====================================================

    def draw(
        self,
        frame,
        current_session=None
    ):

        for track_id, person_bbox in self.tracked_people.items():
            self.draw_person(
                frame,
                track_id,
                person_bbox
            )

        for phone_id, phone_bbox in enumerate(self.detected_phones):
            assigned_track = self.phone_assignments.get(phone_id)
            self.draw_phone(
                frame,
                phone_bbox,
                assigned_track
            )

        self.draw_statistics(
            frame,
            current_session
        )

        return frame

    def get_statistics(self):
        return dict(self._latest_statistics)

    # =====================================================
    # CLEANUP
    # =====================================================

    def cleanup(self):

        current_time = time.time()

        expired_tracks = []

        for track_id, identity in self.identity_cache.items():
            if (
                current_time - identity["last_seen"]
                > self.IDENTITY_CACHE_SECONDS
            ):
                expired_tracks.append(track_id)

        for track_id in expired_tracks:
            self.identity_cache.pop(track_id, None)

        expired_pending = []

        for track_id, pending in self.pending_confirmations.items():
            if (
                current_time - pending["last_confirmation"]
                > self.PENDING_CONFIRMATION_TIMEOUT
            ):
                expired_pending.append(track_id)

        for track_id in expired_pending:
            self.pending_confirmations.pop(track_id, None)

        active_tracks = set(self.tracked_people.keys())

        self.behaviour_tracker.cleanup_inactive_tracks(
            active_tracks
        )

        self.attendance_attempted_tracks = {
            track_id
            for track_id in self.attendance_attempted_tracks
            if track_id in active_tracks
        }
        self.attendance_attempt_times = {
            track_id: attempt_time
            for track_id, attempt_time in self.attendance_attempt_times.items()
            if track_id in active_tracks
        }

        active_phone_ids = set(
            range(len(self.detected_phones))
        )

        self.phone_assignments = {
            phone_id: track_id
            for phone_id, track_id in self.phone_assignments.items()
            if (
                phone_id in active_phone_ids
                and track_id in active_tracks
            )
        }

    # =====================================================
    # PROCESS ENTIRE FRAME
    # =====================================================

    def process(self, frame, current_session=None):
        self.process_yolo(frame)
        self.process_faces(frame)
        self.cleanup()
        self.draw(frame, current_session)

        return frame