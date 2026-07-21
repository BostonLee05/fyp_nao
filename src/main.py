import sys
import time
import qi

from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition

IP = "192.168.0.105"
PORT = 9559


def handle_hello():
    print("Executing hello action!")


def main():
    connection_url = f"tcp://{IP}:{PORT}"
    session = qi.Session()

    try:
        print(f"Connecting to NAO at: {connection_url}")
        session.connect(connection_url)
        print("Successfully connected.")
    except Exception as e:
        print(f"Failed to connect to NAO at: {connection_url}\nError: {e}")
        sys.exit(1)

    # 1. Start Fall Recovery in background thread
    fall = FallRecovery(session)
    fall.start()

    # 2. Start Voice Recognition module
    voice = VoiceRecognition(session)
    voice.register_command("hello", handle_hello)
    voice.start()

    # 3. Main thread sleep loop keeps process alive indefinitely
    print("\n[System] All modules initialized and running continuously.")
    print("[System] Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Shutting down services...")
        fall.stop()
        voice.stop()
        print("[System] Closed successfully.")


if __name__ == "__main__":
    main()