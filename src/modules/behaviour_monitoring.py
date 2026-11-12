import time


# =========================================================
# BEHAVIOUR LABELS
# =========================================================

BEHAVIOUR_FORWARD = "LOOKING_FORWARD"
BEHAVIOUR_LEFT = "LOOKING_LEFT"
BEHAVIOUR_RIGHT = "LOOKING_RIGHT"
BEHAVIOUR_DOWN = "LOOKING_DOWN"
BEHAVIOUR_FACE_NOT_VISIBLE = "FACE_NOT_VISIBLE"
BEHAVIOUR_USING_PHONE = "USING_PHONE"
BEHAVIOUR_UNKNOWN = "UNKNOWN"


# =========================================================
# CONFIGURATION
# =========================================================

# Number of consecutive head-behaviour detections required
# before changing the confirmed head behaviour.
BEHAVIOUR_CONFIRMATIONS_REQUIRED = 3

# Pending head behaviour expires after this duration.
BEHAVIOUR_CONFIRMATION_TIMEOUT = 2.0

# Face is considered not visible after this duration.
FACE_NOT_VISIBLE_SECONDS = 2.0


# -------------------------
# PHONE DETECTION
# -------------------------

# Phone must be detected continuously for this many seconds
# before USING_PHONE is confirmed.
PHONE_CONFIRMATION_SECONDS = 2.0

# After USING_PHONE has been confirmed, the phone must remain
# undetected for this duration before phone usage is cleared.
PHONE_RELEASE_SECONDS = 1.5


# =========================================================
# BEHAVIOUR TRACKER
# =========================================================

class BehaviourTracker:

    def __init__(self):

        # -------------------------------------------------
        # Confirmed head/face behaviour
        # -------------------------------------------------
        #
        # Example:
        #
        # {
        #     1: {
        #         "behaviour": "LOOKING_FORWARD",
        #         "since": timestamp,
        #         "last_face_seen": timestamp
        #     }
        # }

        self.confirmed_behaviours = {}

        # Temporary confirmations before changing
        # head behaviour.
        self.pending_behaviours = {}

        # -------------------------------------------------
        # Phone states
        # -------------------------------------------------
        #
        # Example:
        #
        # {
        #     1: {
        #         "first_detected": timestamp,
        #         "last_detected": timestamp,
        #         "confirmed": True,
        #         "confirmed_since": timestamp
        #     }
        # }

        self.phone_states = {}
        self.phone_history = {}

    # =====================================================
    # ENSURE TRACK EXISTS
    # =====================================================

    def ensure_track(
        self,
        track_id,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        if track_id not in self.confirmed_behaviours:

            self.confirmed_behaviours[track_id] = {
                "behaviour": BEHAVIOUR_UNKNOWN,
                "since": current_time,
                "last_face_seen": current_time
            }

    # =====================================================
    # UPDATE FACE VISIBILITY
    # =====================================================

    def update_face_seen(
        self,
        track_id,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        self.ensure_track(
            track_id,
            current_time
        )

        self.confirmed_behaviours[
            track_id
        ]["last_face_seen"] = current_time

    # =====================================================
    # UPDATE DETECTED HEAD BEHAVIOUR
    # =====================================================

    def update_behaviour(
        self,
        track_id,
        detected_behaviour,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        self.ensure_track(
            track_id,
            current_time
        )

        self.update_face_seen(
            track_id,
            current_time
        )

        current_confirmed = (
            self.confirmed_behaviours[
                track_id
            ]["behaviour"]
        )

        # Already confirmed as this behaviour.
        if current_confirmed == detected_behaviour:

            self.pending_behaviours.pop(
                track_id,
                None
            )

            return current_confirmed

        # ---------------------------------------------
        # Start pending behaviour
        # ---------------------------------------------

        if track_id not in self.pending_behaviours:

            self.pending_behaviours[track_id] = {
                "behaviour": detected_behaviour,
                "count": 1,
                "last_confirmation": current_time
            }

            return current_confirmed

        pending = self.pending_behaviours[
            track_id
        ]

        elapsed = (
            current_time
            - pending["last_confirmation"]
        )

        # ---------------------------------------------
        # Pending confirmation expired
        # ---------------------------------------------

        if elapsed > BEHAVIOUR_CONFIRMATION_TIMEOUT:

            self.pending_behaviours[track_id] = {
                "behaviour": detected_behaviour,
                "count": 1,
                "last_confirmation": current_time
            }

            return current_confirmed

        # ---------------------------------------------
        # Same pending behaviour
        # ---------------------------------------------

        if (
            pending["behaviour"]
            == detected_behaviour
        ):

            pending["count"] += 1

            pending["last_confirmation"] = (
                current_time
            )

        # ---------------------------------------------
        # Different pending behaviour
        # ---------------------------------------------

        else:

            self.pending_behaviours[track_id] = {
                "behaviour": detected_behaviour,
                "count": 1,
                "last_confirmation": current_time
            }

            return current_confirmed

        # ---------------------------------------------
        # Confirm behaviour
        # ---------------------------------------------

        if (
            pending["count"]
            >= BEHAVIOUR_CONFIRMATIONS_REQUIRED
        ):

            old_behaviour = current_confirmed

            self.confirmed_behaviours[
                track_id
            ] = {
                "behaviour": detected_behaviour,
                "since": current_time,
                "last_face_seen": current_time
            }

            del self.pending_behaviours[
                track_id
            ]

            if (
                old_behaviour
                != detected_behaviour
            ):

                print(
                    "\nHEAD BEHAVIOUR CHANGED"
                )

                print(
                    f"Track ID: {track_id}"
                )

                print(
                    f"From: {old_behaviour}"
                )

                print(
                    f"To: {detected_behaviour}"
                )

            return detected_behaviour

        return current_confirmed

    # =====================================================
    # CHECK FACE VISIBILITY
    # =====================================================

    def check_face_visibility(
        self,
        active_track_ids,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        for track_id in active_track_ids:

            self.ensure_track(
                track_id,
                current_time
            )

            data = self.confirmed_behaviours[
                track_id
            ]

            elapsed = (
                current_time
                - data["last_face_seen"]
            )

            if (
                elapsed
                >= FACE_NOT_VISIBLE_SECONDS
                and data["behaviour"]
                != BEHAVIOUR_FACE_NOT_VISIBLE
            ):

                old_behaviour = data[
                    "behaviour"
                ]

                data["behaviour"] = (
                    BEHAVIOUR_FACE_NOT_VISIBLE
                )

                data["since"] = (
                    current_time
                )

                self.pending_behaviours.pop(
                    track_id,
                    None
                )

                print(
                    "\nHEAD BEHAVIOUR CHANGED"
                )

                print(
                    f"Track ID: {track_id}"
                )

                print(
                    f"From: {old_behaviour}"
                )

                print(
                    "To: FACE_NOT_VISIBLE"
                )

    # =====================================================
    # UPDATE PHONE DETECTION
    # =====================================================

    def update_phone_detection(
        self,
        track_id,
        phone_detected,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        self.ensure_track(
            track_id,
            current_time
        )

        # ---------------------------------------------
        # Phone currently detected
        # ---------------------------------------------

        if phone_detected:

            if track_id not in self.phone_states:

                self.phone_states[track_id] = {
                    "first_detected": current_time,
                    "last_detected": current_time,
                    "confirmed": False,
                    "confirmed_since": None,
                    "usage_counted": False
                }

                return False

            phone_state = self.phone_states[
                track_id
            ]

            # If the previous detection was too long ago,
            # begin a new confirmation period.
            time_since_last_detection = (
                current_time
                - phone_state["last_detected"]
            )

            if (
                not phone_state["confirmed"]
                and time_since_last_detection
                > PHONE_RELEASE_SECONDS
            ):

                phone_state[
                    "first_detected"
                ] = current_time

            phone_state[
                "last_detected"
            ] = current_time

            # Confirm phone usage after the required
            # continuous detection duration.
            if not phone_state["confirmed"]:

                detection_duration = (
                    current_time
                    - phone_state["first_detected"]
                )

                if (
                    detection_duration
                    >= PHONE_CONFIRMATION_SECONDS
                ):

                    phone_state[
                        "confirmed"
                    ] = True

                    phone_state[
                        "confirmed_since"
                    ] = current_time
                    phone_state["usage_counted"] = True

                    history = self.phone_history.setdefault(
                        track_id,
                        {"count": 0, "total_duration": 0.0}
                    )
                    history["count"] += 1

                    print(
                        "\nPHONE USAGE CONFIRMED"
                    )

                    print(
                        f"Track ID: {track_id}"
                    )

                    print(
                        "Behaviour: USING_PHONE"
                    )

            return phone_state[
                "confirmed"
            ]

        # ---------------------------------------------
        # Phone not detected in this update
        # ---------------------------------------------

        if track_id not in self.phone_states:

            return False

        phone_state = self.phone_states[
            track_id
        ]

        time_since_last_detection = (
            current_time
            - phone_state["last_detected"]
        )

        # Keep confirmed phone usage active briefly,
        # because YOLO may miss the phone for some frames.
        if phone_state["confirmed"]:

            if (
                time_since_last_detection
                < PHONE_RELEASE_SECONDS
            ):

                return True

            print(
                "\nPHONE USAGE ENDED"
            )

            print(
                f"Track ID: {track_id}"
            )

            if phone_state["confirmed_since"] is not None:
                history = self.phone_history.setdefault(
                    track_id,
                    {"count": 0, "total_duration": 0.0}
                )
                history["total_duration"] += max(
                    0.0,
                    phone_state["last_detected"]
                    - phone_state["confirmed_since"]
                )

            del self.phone_states[
                track_id
            ]

            return False

        # Pending but not yet confirmed.
        if (
            time_since_last_detection
            >= PHONE_RELEASE_SECONDS
        ):

            del self.phone_states[
                track_id
            ]

        return False

    # =====================================================
    # IS USING PHONE
    # =====================================================

    def is_using_phone(
        self,
        track_id,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        phone_state = self.phone_states.get(
            track_id
        )

        if phone_state is None:

            return False

        if not phone_state["confirmed"]:

            return False

        time_since_last_detection = (
            current_time
            - phone_state["last_detected"]
        )

        return (
            time_since_last_detection
            < PHONE_RELEASE_SECONDS
        )

    # =====================================================
    # GET FINAL DISPLAY BEHAVIOUR
    # =====================================================

    def get_behaviour(
        self,
        track_id,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        # Phone usage has priority over head behaviour.
        if self.is_using_phone(
            track_id,
            current_time
        ):

            return BEHAVIOUR_USING_PHONE

        data = self.confirmed_behaviours.get(
            track_id
        )

        if data is None:

            return BEHAVIOUR_UNKNOWN

        return data["behaviour"]

    # =====================================================
    # GET BEHAVIOUR DURATION
    # =====================================================

    def get_behaviour_duration(
        self,
        track_id,
        current_time=None
    ):

        if current_time is None:
            current_time = time.time()

        # ---------------------------------------------
        # Phone duration
        # ---------------------------------------------

        if self.is_using_phone(
            track_id,
            current_time
        ):

            phone_state = self.phone_states[
                track_id
            ]

            confirmed_since = phone_state[
                "confirmed_since"
            ]

            if confirmed_since is None:
                return 0.0

            return max(
                0.0,
                current_time - confirmed_since
            )

        # ---------------------------------------------
        # Head behaviour duration
        # ---------------------------------------------

        data = self.confirmed_behaviours.get(
            track_id
        )

        if data is None:
            return 0.0

        return max(
            0.0,
            current_time - data["since"]
        )

    # =====================================================
    # REMOVE INACTIVE TRACKS
    # =====================================================

    def cleanup_inactive_tracks(
        self,
        active_track_ids
    ):

        active_track_ids = set(
            active_track_ids
        )

        stored_ids = list(
            self.confirmed_behaviours.keys()
        )

        for track_id in stored_ids:

            if track_id not in active_track_ids:

                del self.confirmed_behaviours[
                    track_id
                ]

                self.pending_behaviours.pop(
                    track_id,
                    None
                )

                phone_state = self.phone_states.get(track_id)
                if (
                    phone_state is not None
                    and phone_state["confirmed_since"] is not None
                ):
                    history = self.phone_history.setdefault(
                        track_id,
                        {"count": 0, "total_duration": 0.0}
                    )
                    history["total_duration"] += max(
                        0.0,
                        phone_state["last_detected"]
                        - phone_state["confirmed_since"]
                    )

                self.phone_states.pop(
                    track_id,
                    None
                )