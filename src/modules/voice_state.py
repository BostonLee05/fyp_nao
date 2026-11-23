from collections import deque
from datetime import datetime
from threading import RLock
from typing import Any, Deque, Dict, List, Optional

class VoiceState:
    """Thread-safe state shared by wake audio, voice recognition, and Flask."""

    def __init__(self, max_history: int = 30) -> None:
        self._lock = RLock()
        self._max_history = max_history
        self._status = "Ready/listening again"
        self._latest_command = ""
        self._latest_result = ""
        self._latest_action = ""
        self._latest_error = ""
        self._speaking = False
        self._animation_enabled = True
        self._recommendations = []
        self._recommendation_token = 0
        self._history: Deque[Dict[str, Any]] = deque(maxlen=max_history)

    def set_status(self, status: str, error: str = "") -> None:
        with self._lock:
            self._status = status
            self._latest_error = error or ""

    def set_speaking(self, speaking: bool) -> None:
        with self._lock:
            self._speaking = bool(speaking)

    def set_animation_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._animation_enabled = bool(enabled)

    def is_animation_enabled(self) -> bool:
        with self._lock:
            return self._animation_enabled

    def record_command(
        self,
        command: str,
        action: str,
        result: str,
        status: str = "Completed",
        recommendations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        with self._lock:
            timestamp = datetime.now()
            self._latest_command = command or ""
            self._latest_action = action or ""
            self._latest_result = result or ""
            self._latest_error = "" if status == "Completed" else (result or "")

            entry = {
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "time": timestamp.strftime("%H:%M"),
                "command": self._latest_command,
                "action": self._latest_action,
                "result": self._latest_result,
                "status": status,
            }
            self._history.appendleft(entry)

            if recommendations is not None:
                self._recommendations = list(recommendations)
                self._recommendation_token += 1

    def set_recommendations(self, recommendations: Optional[List[Dict[str, Any]]]) -> None:
        with self._lock:
            self._recommendations = list(recommendations or [])
            self._recommendation_token += 1

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "latest_command": self._latest_command,
                "latest_result": self._latest_result,
                "latest_action": self._latest_action,
                "latest_error": self._latest_error,
                "speaking": self._speaking,
                "animation_enabled": self._animation_enabled,
                "history": list(self._history),
                "recommendations": list(self._recommendations),
                "recommendation_token": self._recommendation_token,
            }


voice_state = VoiceState()
