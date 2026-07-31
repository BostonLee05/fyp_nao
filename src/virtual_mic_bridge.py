import io
import wave
import sys
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import qi


def capture_audio(duration=4, samplerate=16000):
    """Records audio from laptop mic using sounddevice."""
    print("\n Listening... Speak your command (4s window):")
    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
    sd.wait()  # Wait for recording to complete

    # Save audio stream to memory (WAV format)
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(recording.tobytes())

    wav_io.seek(0)
    return wav_io


def main():
    # 1. Connect to Virtual NAO
    session = qi.Session()
    try:
        session.connect("tcp://127.0.0.1:9559")
        print(" Connected to Virtual NAOqi!")
    except Exception as e:
        print(f" Could not connect to NAOqi: {e}")
        sys.exit(1)

    memory_service = session.service("ALMemory")
    dialog_service = session.service("ALDialog")
    recognizer = sr.Recognizer()

    print("\n--- Virtual NAO Continuous Mic Bridge Started ---")
    print(" Press Ctrl+C in terminal to stop anytime.\n")

    # 2. Continuous Always-On Loop
    try:
        while True:
            # Record 4 seconds of audio from laptop mic
            audio_stream = capture_audio(duration=4)

            try:
                # Transcribe audio to text
                with sr.AudioFile(audio_stream) as source:
                    audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data)
                    print(f" Recognized: '{text}'")

                    # Forward recognized text to Virtual NAO
                    dialog_service.forceInput(text)
                    memory_service.raiseEvent("WordRecognized", [text, 0.95])
                    print(" Sent to Virtual NAO!")

            except sr.UnknownValueError:
                # Triggered when no speech or background noise was captured
                print(" [No clear speech heard]")
            except sr.RequestError as e:
                print(f" Speech API service error: {e}")
            except Exception as e:
                print(f" Error: {e}")

    except KeyboardInterrupt:
        print("\n Stopped microphone bridge. Goodbye!")


if __name__ == "__main__":
    main()