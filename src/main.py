import sys
import time
import qi
from flask import Flask, render_template, request, jsonify

from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition

app = Flask(__name__)

IP = "192.168.0.106"
PORT = 9559

# Global references for your robot services
session = None
fall = None
voice = None


def handle_hello():
    print("Executing hello action!")


def initialize_robot():
    global session

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
        # Pull the ALTextToSpeech service using the global qi session
        tts = session.service("ALTextToSpeech")
        tts.say(str(text))
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
