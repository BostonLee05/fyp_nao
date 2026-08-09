"""
robot.py
Central Robot Session Manager for the NAO Smart Classroom system.
Ps. Not sure what this need ornot yet
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from threading import RLock
import uuid


@dataclass
class SessionState:
    connected: bool = False
    robot_ip: str | None = None
    session_id: str | None = None
    session_start: datetime | None = None
    session_duration: int | None = None   # seconds; None = unlimited
    disconnect_time: datetime | None = None
    disconnect_reason: str = ""
    last_disconnect_reason: str = ""
    last_disconnect_at: datetime | None = None


class RobotSessionManager:
    """Singleton-style manager that stores the robot connection state."""

    def __init__(self):
        self._lock = RLock()
        self._state = SessionState()

    # ---------- Connection ----------
    def start_session(self, robot_ip: str, duration_seconds: int | None = None):
        """Create a new robot session."""
        with self._lock:
            now = datetime.now()

            self._state.connected = True
            self._state.robot_ip = robot_ip
            self._state.session_id = str(uuid.uuid4())[:8].upper()
            self._state.session_start = now
            self._state.session_duration = duration_seconds
            self._state.disconnect_reason = ""

            if duration_seconds is None:
                self._state.disconnect_time = None
            else:
                self._state.disconnect_time = now + timedelta(seconds=duration_seconds)

    def stop_session(self, reason: str = "Manual Disconnect"):
        """Terminate the current session."""
        with self._lock:
            self._state.connected = False
            self._state.last_disconnect_reason = reason
            self._state.last_disconnect_at = datetime.now()
            self._state.disconnect_reason = reason

            self._state.robot_ip = None
            self._state.session_id = None
            self._state.session_start = None
            self._state.session_duration = None
            self._state.disconnect_time = None

    # ---------- Status ----------
    def is_connected(self) -> bool:
        with self._lock:
            return self._state.connected

    def get_remaining_seconds(self):
        with self._lock:
            if not self._state.connected:
                return 0

            if self._state.disconnect_time is None:
                return None

            remaining = int((self._state.disconnect_time - datetime.now()).total_seconds())
            return max(remaining, 0)

    def has_expired(self) -> bool:
        remaining = self.get_remaining_seconds()
        if remaining is None:
            return False
        return remaining <= 0

    def check_timeout(self):
        """Call this periodically from a background thread."""
        if self.has_expired():
            self.stop_session("Timer Expired")
            return True
        return False

    # ---------- Getters ----------
    def get_status(self):
        with self._lock:
            return {
                "connected": self._state.connected,
                "robot_ip": self._state.robot_ip,
                "session_id": self._state.session_id,
                "remaining_seconds": self.get_remaining_seconds(),
                "remaining": self.formatted_remaining(),
                "disconnect_reason": self._state.disconnect_reason,
                "last_disconnect_reason": self._state.last_disconnect_reason,
                "disconnect_at": (
                    self._state.disconnect_time.isoformat()
                    if self._state.disconnect_time else None
                ),
            }

    def export(self):
        """Return the raw session state as a serialisable dictionary."""
        with self._lock:
            data = asdict(self._state)
            for k, v in list(data.items()):
                if isinstance(v, datetime):
                    data[k] = v.isoformat()
            return data

    # ---------- Convenience ----------
    def formatted_remaining(self):
        sec = self.get_remaining_seconds()

        if sec is None:
            return "Unlimited"

        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)

        if h:
            return f"{h:02}:{m:02}:{s:02}"

        return f"{m:02}:{s:02}"


# Singleton instance used by the whole Flask application
robot_session = RobotSessionManager()
