import sys
import time

import qi

from modules.voice_recognition import VoiceRecognition
from modules.wake_audio import WakeAudio
from speaker import Speaker


TOPIC_CONTENT = """topic: ~wake_audio_virtual_test()
language: enu
u:(["hey nao" "hey now" "hi now" "hello nao" "hello now"]) $WakeAudio/WakeWord=$Dialog/LastInput
"""


def main():
    session = qi.Session()
    try:
        session.connect("tcp://127.0.0.1:9559")
    except Exception as e:
        print(f"[VirtualWakeTest] Could not connect to virtual NAOqi: {e}")
        sys.exit(1)

    dialog = None
    topic_name = None
    dialog_subscribed = False

    try:
        dialog = session.service("ALDialog")
        dialog.setLanguage("English")
        topic_name = dialog.loadTopicContent(TOPIC_CONTENT)
        dialog.activateTopic(topic_name)
        dialog.subscribe("VirtualWakeTest")
        dialog_subscribed = True
        print(f"[VirtualWakeTest] Loaded dialog topic: {topic_name}")
    except Exception as e:
        print(f"[VirtualWakeTest Warning] Dialog topic was not loaded: {e}")

    speaker = Speaker(session, force_virtual=True)
    voice = VoiceRecognition(session=session, speaker=speaker, use_test_audio=False)
    wake_audio = WakeAudio(session, speaker, voice)
    wake_audio.start()

    print("[VirtualWakeTest] Ready.")
    print("[VirtualWakeTest] Say/type: hey nao, hey now, or hi now.")
    print("[VirtualWakeTest] Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        wake_audio.stop()
        voice.stop()

        if dialog:
            try:
                if dialog_subscribed:
                    dialog.unsubscribe("VirtualWakeTest")
            except Exception:
                pass

            try:
                if topic_name:
                    dialog.deactivateTopic(topic_name)
            except Exception:
                pass

            try:
                if topic_name:
                    dialog.unloadTopic(topic_name)
            except Exception:
                pass

        try:
            session.close()
        except Exception:
            pass
        print("[VirtualWakeTest] Stopped.")


if __name__ == "__main__":
    main()
