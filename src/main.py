import sys
import time
import qi
from flask import Flask, render_template, request, jsonify

from speaker import Speaker
from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition

app = Flask(__name__)

IP = "127.0.0.1"
PORT = 9559

session = None
speaker = None
fall = None
voice = None

def say_hello():
    speaker.speak("Hello there! I am talking to you through your laptop.")

def start_dance():
    print("[Dance] Checking for installed behaviors...")

    try:
        bm = session.service("ALBehaviorManager")
        installed_behaviors = bm.getInstalledBehaviors()
        print(f"[Dance] Installed behaviors on robot: {installed_behaviors}")

        taichi_behavior = None

        # 1. Search for explicit 'taichi' keyword in behavior names
        for b in installed_behaviors:
            if any(
                keyword in b.lower()
                for keyword in ["taichi", "tai-chi", "tai_chi"]
            ):
                taichi_behavior = b
                break

        # 2. Fallback: Grab the Choregraphe uploaded behavior
        if not taichi_behavior:
            for b in installed_behaviors:
                if (
                    "lastuploadedchoregraphebehavior" in b.lower()
                    or "behavior_1" in b.lower()
                ):
                    taichi_behavior = b
                    break

        if taichi_behavior:
            # FIX: If the behavior is currently running in Choregraphe, stop it first
            if bm.isBehaviorRunning(taichi_behavior):
                print(
                    f"[Dance] Behavior '{taichi_behavior}' is already running."
                    " Restarting it..."
                )
                bm.stopBehavior(taichi_behavior)
                time.sleep(0.5)

            speaker.speak("Starting Tai Chi routine! Stand back.")
            print(f"[Dance] Running behavior: '{taichi_behavior}'")

            # Execute behavior (blocks until finished)
            bm.runBehavior(taichi_behavior)

            speaker.speak("Finished my Tai Chi routine!")
        else:
            print("[Dance] No dance behavior found in ALBehaviorManager.")
            speaker.speak("The Tai Chi behavior is not installed on this robot.")

    except Exception as e:
        print(f"[Dance Error] {e}")
        speaker.speak("Sorry, I encountered an error while trying to dance.")
def initialize_robot():
    global session, speaker, fall, voice

    connection_url = f"tcp://{IP}:{PORT}"
    session = qi.Session()

    try:
        print(f"Connecting to NAO at: {connection_url}")
        session.connect(connection_url)
        print("Successfully connected.")
    except Exception as e:
        print(f"Failed to connect to NAO at: {connection_url}\nError: {e}")
        sys.exit(1)

    speaker = Speaker(session)

    # 1. Start Fall Recovery in background thread
    fall = FallRecovery(session, speaker)
    fall.start()

    # 2. Start Voice Recognition module
    voice = VoiceRecognition(session, speaker)
    voice.register_command("hello",say_hello)
    voice.register_command("tai chi", start_dance)
    voice.start()

    print("\n[System] All robot modules initialized and running continuously.")


# --- Flask Web Routes ---

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/say', methods=['POST'])
def say_something():
    data = request.get_json()
    text = data.get('text', '')

    try:
        speaker.speak(str(text))
        return jsonify({"status": "success", "message": "NAO spoke."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to speak: {e}"})


# --- Application Entry Point ---

if __name__ == "__main__":
    # First, spin up all robot configurations and background threads
    initialize_robot()

    # Second, hand over control to Flask.
    print("[System] Launching web server. Press Ctrl+C to stop.")
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        # Triggers cleanly when you shut down the Flask server
        print("\n[System] Shutting down services...")
        if fall:
            fall.stop()
        if voice:
            voice.stop()
        print("[System] Closed successfully.")
