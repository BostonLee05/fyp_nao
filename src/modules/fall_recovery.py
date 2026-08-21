import threading
import time


class FallRecovery(threading.Thread):

    def __init__(self, session, speaker):
        super(FallRecovery, self).__init__()
        self.daemon = True
        self.session = session
        self.speaker = speaker

        self.motion = self.session.service("ALMotion")
        self.posture = self.session.service("ALRobotPosture")

        self.running = False
        self.is_recovering = False  # Lock to prevent multiple simultaneous triggers
        self.is_recovering = (
            False  # Lock to prevent multiple simultaneous triggers
        )

    def _get_service(self, name):
        """Safely fetch a NAOqi service proxy on demand."""
        try:
            if self.session and self.session.isConnected():
                return self.session.service(name)
        except Exception:
            pass
        return None

    def run(self):
        self.running = True
        print("[FallRecovery] Daemon started. Monitoring posture in background...")
        print(
            "[FallRecovery] Daemon started. Monitoring posture in background..."
        )

        fall_postures = ["LyingBelly", "LyingBack", "LyingLeft", "LyingRight", "Belly", "Back", "Lying"]
        fall_postures = [
            "LyingBelly",
            "LyingBack",
            "LyingLeft",
            "LyingRight",
            "Belly",
            "Back",
            "Lying",
        ]

        while self.running:
            try:
                current_family = self.posture.getPostureFamily()
                # 1. Validate active connection before querying services
                posture = self._get_service("ALRobotPosture")
                if not posture:
                    time.sleep(2.0)
                    continue

                current_family = posture.getPostureFamily()

                if current_family in fall_postures and not self.is_recovering:
                    self.is_recovering = True
                    print(f"[FallRecovery] ALERT: Fall detected! Posture: {current_family}")
                    print(
                        f"[FallRecovery] ALERT: Fall detected! Posture: {current_family}"
                    )

                    # 1. Stop active behaviors
                    try:
                        bm = self.session.service("ALBehaviorManager")
                        if bm.getRunningBehaviors():
                            print("[FallRecovery] Stopping active behaviors...")
                            bm.stopAllBehaviors()
                    except Exception as e:
                        print(f"[FallRecovery] Error stopping behaviors: {e}")
                    motion = self._get_service("ALMotion")
                    bm = self._get_service("ALBehaviorManager")

                    # 2. Stop active behaviors
                    if bm:
                        try:
                            if bm.getRunningBehaviors():
                                print(
                                    "[FallRecovery] Stopping active behaviors..."
                                )
                                bm.stopAllBehaviors()
                        except Exception as e:
                            print(
                                f"[FallRecovery] Error stopping behaviors: {e}"
                            )

                    # 2. Kill active motion tasks
                    try:
                        self.motion.killAll()
                    except Exception as e:
                        print(f"[FallRecovery] Error killing motions: {e}")
                    # 3. Kill active motion tasks
                    if motion:
                        try:
                            motion.killAll()
                        except Exception as e:
                            print(f"[FallRecovery] Error killing motions: {e}")

                    time.sleep(0.5)

                    # 3. Notify user
                    # 4. Notify user
                    try:
                        self.speaker.speak("Oops! I have fallen down. Stopping all movements to stand up.")
                        self.speaker.speak(
                            "Oops! I have fallen down. Stopping all movements to stand up."
                        )
                    except Exception as e:
                        print(f"[FallRecovery] Error speaking: {e}")

                    # 4. Turn stiffness back ON directly (Replaces wakeUp)
                    # 5. Turn stiffness back ON directly
                    print("[FallRecovery] Enabling motor stiffness...")
                    try:
                        self.motion.setStiffnesses("Body", 1.0)
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"[FallRecovery] Error setting stiffness: {e}")
                    if motion:
                        try:
                            motion.setStiffnesses("Body", 1.0)
                            time.sleep(0.5)
                        except Exception as e:
                            print(
                                f"[FallRecovery] Error setting stiffness: {e}"
                            )

                    # 5. Attempt standing posture (ALRobotPosture handles recovery routines)
                    # 6. Attempt standing posture
                    print("[FallRecovery] Attempting stand recovery...")
                    try:
                        success = self.posture.goToPosture("StandInit", 0.6)
                        success = posture.goToPosture("StandInit", 0.6)

                        if success:
                            print("[FallRecovery] Fall recovered successfully!")
                            self.speaker.speak("I am back on my feet and ready to go.")
                            self.speaker.speak(
                                "I am back on my feet and ready to go."
                            )
                        else:
                            print("[FallRecovery] Recovery failed.")
                            self.speaker.speak("I could not stand up. Please check my joints.")
                            self.speaker.speak(
                                "I could not stand up. Please check my joints."
                            )
                    except Exception as e:
                        print(f"[FallRecovery] Error during posture recovery: {e}")
                        print(
                            f"[FallRecovery] Error during posture recovery: {e}"
                        )

                    time.sleep(5.0)
                    self.is_recovering = False

            except Exception as e:
                print(f"[FallRecovery] Loop Error: {e}")
                # Prevents socket exceptions from crashing the thread or flooding stdout rapidly
                print(f"[FallRecovery] Connection issue encountered: {e}")
                time.sleep(2.0)

            time.sleep(1.0)

    def stop(self):
        self.running = False
        self.is_recovering = False
