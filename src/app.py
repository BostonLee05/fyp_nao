import qi
import sys
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Replace with your actual NAO robot IP address
ROBOT_IP = "192.168.0.106"
PORT = "9559"

# Initialize the qi session
session = qi.Session()
try:
    # Connect to the robot using the required tcp:// URL format
    session.connect(f"tcp://{ROBOT_IP}:{PORT}")
    print("Successfully connected to NAO via qi framework!")
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/say', methods=['POST'])
def say_something():
    data = request.get_json()
    text = data.get('text', '')

    try:
        # Retrieve the text-to-speech service through the qi session
        tts = session.service("ALTextToSpeech")
        tts.say(str(text))
        return jsonify({"status": "success", "message": "NAO spoke."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to speak: {e}"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
