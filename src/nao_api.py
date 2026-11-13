"""
nao_api.py

Centralized NAO Robot API Manager

This file is the ONLY place that should communicate directly
with qi.Session().

All other modules should use:

    robot_api = get_nao_manager()

instead of creating their own qi.Session().
"""

from typing import Any, Optional
import time
import threading
import logging

try:
    import qi
except ImportError:  # pragma: no cover - environment dependent
    qi = None

logger = logging.getLogger(__name__)


class NAOManager:
    """Singleton manager for the NAO robot.

    Responsibilities:
    - Manage a single qi.Session shared across the app
    - Provide safe service lookups
    - Verify connection after connect
    - Gracefully disconnect
    """

    def __init__(self):

        # ----------------------------
        # Robot Session
        # ----------------------------

        self._session: Optional[Any] = None
        self._lock = threading.RLock()

        # ----------------------------
        # Cached NAO Services
        # ----------------------------

        self._services = {}

        # ----------------------------
        # Robot Information
        # ----------------------------

        self.robot_ip: Optional[str] = None
        self.robot_port: int = 9559

    # ==========================================================
    # Connection
    # ==========================================================

    def connect(self, robot_ip: str, robot_port: int = 9559, retries: int = 3, delay: float = 1.0):
        """
        Connect to the robot. If already connected to the same IP/port, do nothing.

        Raises RuntimeError on failure.
        """

        if qi is None:
            raise RuntimeError("qi is not available in this environment.")

        with self._lock:
            if self.is_connected():
                # Already connected
                if self.robot_ip == robot_ip and self.robot_port == robot_port:
                    return
                # Different target: disconnect first
                self.disconnect()

            self.robot_ip = robot_ip
            self.robot_port = robot_port

            last_exc: Optional[Exception] = None
            for attempt in range(1, retries + 1):
                session = qi.Session()
                try:
                    session.connect(f"tcp://{robot_ip}:{robot_port}")

                    # Save session only on success
                    self._session = session

                    # Load and verify services
                    try:
                        self._load_services()
                        self.verify_connection()
                    except Exception:
                        # If verification failed, close session and retry
                        try:
                            session.close()
                        except Exception:
                            pass
                        self._session = None
                        raise

                    # Connected and verified
                    logger.info("Connected to NAO at %s:%s", robot_ip, robot_port)
                    break

                except Exception as e:
                    last_exc = e
                    logger.warning("Connection attempt %s failed: %s", attempt, e)
                    time.sleep(delay)
            else:
                # All attempts failed
                raise RuntimeError(f"Unable to connect to robot {robot_ip}:{robot_port}: {last_exc}")

            # Print summary
            try:
                print("=" * 60)
                print(" NAO ROBOT CONNECTED")
                print("=" * 60)
                print(f"IP        : {self.robot_ip}")
                print(f"Version   : {self.get_robot_version()}")
                print(f"Battery   : {self.get_battery_percentage()}%")
                print("=" * 60)

                # Greeting (non-fatal)
                try:
                    self.say("Connection established. Welcome to the Smart Classroom.")
                except Exception as e:
                    logger.info("TTS greeting failed: %s", e)

            except Exception:
                # Avoid letting logging/printing break the connection
                pass

    def connect_with_virtual_fallback(
        self,
        robot_ip: str,
        robot_port: int = 9559,
        virtual_ip: str = "127.0.0.1",
        virtual_port: int = 9559,
    ) -> tuple[str, int, bool]:
        """Connect to the requested NAO, then try Choregraphe's virtual NAO.

        Returns ``(connected_ip, connected_port, used_virtual_fallback)``.
        The fallback is only attempted when the requested endpoint fails.
        """
        try:
            self.connect(robot_ip, robot_port)
            return robot_ip, robot_port, False
        except Exception as real_error:
            logger.warning(
                "NAO endpoint %s:%s unavailable; trying Choregraphe virtual NAO at %s:%s: %s",
                robot_ip, robot_port, virtual_ip, virtual_port, real_error,
            )

        if robot_ip == virtual_ip and robot_port == virtual_port:
            raise RuntimeError(f"Unable to connect to NAO at {robot_ip}:{robot_port}")

        self.connect(virtual_ip, virtual_port)
        return virtual_ip, virtual_port, True

    def disconnect(self):
        """Disconnect from robot and clear cached services."""

        with self._lock:
            if self._session is None:
                return

            try:
                # Best-effort farewell
                try:
                    if "tts" in self._services:
                        self._services["tts"].say("Robot disconnected. Goodbye.")
                except Exception:
                    pass

                try:
                    self._session.close()
                except Exception:
                    pass

            finally:
                self._session = None
                self._services.clear()
                logger.info("Disconnected from NAO")

    def is_connected(self) -> bool:
        """Return whether the cached NAOqi session is still connected."""

        with self._lock:
            if self._session is None:
                return False

            try:
                return bool(self._session.isConnected())
            except Exception:
                return False

    # ==========================================================
    # Session
    # ==========================================================

    def get_session(self):
        if self._session is None:
            raise RuntimeError("Robot is not connected.")
        return self._session

    # ==========================================================
    # Services
    # ==========================================================

    def _load_services(self):
        """Cache commonly-used NAO services. Raises on failure to obtain essential services."""

        session = self.get_session()

        needed = {
            "tts": "ALTextToSpeech",
            "memory": "ALMemory",
            "system": "ALSystem",
        }

        services = {}

        # ALAnimatedSpeech adds coordinated NAO gestures while preserving the
        # same ``say`` interface. It is optional so older robots can still use
        # ALTextToSpeech.
        try:
            services["animated_tts"] = session.service("ALAnimatedSpeech")
        except Exception:
            services["animated_tts"] = None

        optional = {
            "motion": "ALMotion",
            "posture": "ALRobotPosture",
            "life": "ALAutonomousLife",
        }

        # Load required services
        for key, name in needed.items():
            try:
                services[key] = session.service(name)
            except Exception as e:
                raise RuntimeError(f"Required service {name} unavailable: {e}")

        # Load optional services (best-effort)
        for key, name in optional.items():
            try:
                services[key] = session.service(name)
            except Exception:
                services[key] = None

        self._services = services

    def get_service(self, service_name: str):
        """Return cached service when known, otherwise fetch from session."""

        lookup = {
            "ALTextToSpeech": "tts",
            "ALMemory": "memory",
            "ALSystem": "system",
            "ALMotion": "motion",
            "ALRobotPosture": "posture",
            "ALAutonomousLife": "life",
        }

        key = lookup.get(service_name)

        if key:
            svc = self._services.get(key)
            if svc is None:
                # service was optional and not present
                raise RuntimeError(f"Service {service_name} is not available")
            return svc

        # Fallback: try to fetch directly
        return self.get_session().service(service_name)

    # ==========================================================
    # Verification
    # ==========================================================

    def verify_connection(self) -> bool:
        """Verify that the robot connection is alive by checking memory keys known to exist on NAO.

        Raises RuntimeError if verification fails.
        """

        if self._session is None:
            raise RuntimeError("Robot is not connected.")

        memory = self._services.get("memory")
        if memory is None:
            raise RuntimeError("ALMemory service not available for verification")

        candidates = [
            "Device/DeviceList/ChestBoard/BodyId",
            "Device/SerialNumber",
            "Device/SubDeviceList/ChestBoard/BodyId",
        ]

        last_exc: Optional[Exception] = None
        for key in candidates:
            try:
                val = memory.getData(key)
                # successful read
                logger.debug("verify_connection read %s => %s", key, val)
                return True
            except Exception as e:
                last_exc = e

        raise RuntimeError(f"Robot connection verification failed: {last_exc}")

    # ==========================================================
    # Speech
    # ==========================================================

    def say(self, text: str) -> None:
        """Speak text using ALTextToSpeech. Non-fatal: logs failures but raises only if not connected."""

        if not text:
            return

        if not self.is_connected():
            raise RuntimeError("Cannot speak: robot is not connected")

        tts = self._services.get("animated_tts") or self._services.get("tts")
        if tts is None:
            raise RuntimeError("ALTextToSpeech service not available")

        try:
            if tts is self._services.get("animated_tts"):
                try:
                    tts.setBodyLanguageMode("contextual")
                except Exception:
                    pass
                text = f"^start(animations/Stand/Gestures/Explain_1) {str(text).replace('^', '')}"
            tts.say(text)
        except Exception as e:
            logger.exception("TTS failed: %s", e)
            # Don't raise to avoid taking down callers; caller can check logs

    # ==========================================================
    # Robot Information
    # ==========================================================

    def get_robot_name(self) -> str:
        try:
            system = self._services.get("system")
            if system is None:
                return "Unknown"
            return system.robotName()
        except Exception:
            return "Unknown"

    def get_robot_version(self) -> str:
        try:
            system = self._services.get("system")
            if system is None:
                return "Unknown"
            return system.systemVersion()
        except Exception:
            return "Unknown"

    def get_battery_percentage(self) -> int:
        """
        Returns battery percentage (0~100), or -1 if unavailable.
        """

        try:
            memory = self._services.get("memory")
            if memory is None:
                return -1

            value = memory.getData("Device/SubDeviceList/Battery/Charge/Sensor/Value")
            if value is None:
                return -1

            # Value may already be 0-100 or 0.0-1.0 depending on firmware
            if isinstance(value, (int, float)):
                if 0 <= value <= 1:
                    return int(round(value * 100))
                if 0 <= value <= 100:
                    return int(round(value))

            return -1
        except Exception:
            return -1

    def get_robot_info(self):
        """Returns robot information as a dictionary."""

        return {
            "connected": self.is_connected(),
            "robot_ip": self.robot_ip,
            "robot_port": self.robot_port,
            "robot_name": self.get_robot_name(),
            "robot_version": self.get_robot_version(),
            "battery": self.get_battery_percentage(),
        }

    # ==========================================================
    # Motion
    # ==========================================================

    def wake_up(self):
        self.get_service("ALMotion").wakeUp()

    def rest(self):
        self.get_service("ALMotion").rest()

    # ==========================================================
    # Autonomous Life
    # ==========================================================

    def enable_autonomous_life(self):
        self.get_service("ALAutonomousLife").setState("interactive")

    def disable_autonomous_life(self):
        self.get_service("ALAutonomousLife").setState("disabled")


# ==========================================================
# Singleton
# ==========================================================

_manager: Optional[NAOManager] = None
_manager_lock = threading.Lock()


def get_nao_manager() -> NAOManager:
    """Returns the singleton NAOManager."""

    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = NAOManager()
        return _manager
