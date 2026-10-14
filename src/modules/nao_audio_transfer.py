import os
import posixpath
import time
import wave
from pathlib import Path

class NAOAudioTransfer:
    """Handles NAO audio capture, download, and local test-audio fallback."""

    def __init__(
        self,
        audio_recorder=None,
        file_manager=None,
        remote_path="/home/nao/nao_speech.wav",
        local_path=None,
        test_audio_path=None,
        use_test_audio=True,
    ):
        self.audio_recorder = audio_recorder
        self.file_manager = file_manager
        self.remote_path = remote_path
        self.local_path = local_path
        self.test_audio_path = test_audio_path
        self.use_test_audio = use_test_audio

    def record_from_nao(self, duration):
        """Records audio on NAO and downloads it to the local machine."""
        if not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None

        try:
            self.remote_path = self._get_recording_remote_path()
            print(f"[NAOAudioTransfer] Recording on NAO: {self.remote_path}")
            self.audio_recorder.startMicrophonesRecording(
                self.remote_path, "wav", 16000, [1, 1, 1, 1]
            )

            print(f"[NAOAudioTransfer] Recording for {duration} seconds...")
            time.sleep(duration)

            self.audio_recorder.stopMicrophonesRecording()
            print("[NAOAudioTransfer] NAO recording stopped.")

            return self.download()
        except Exception as e:
            print(f"[NAOAudioTransfer Error] Failed to record from NAO: {e}")
            return None

    def record_until_silence(
        self,
        speech_detector,
        chunk_duration=0.25,
        start_timeout=8,
        silence_duration=1.2,
        max_duration=20,
    ):
        """Capture short NAO chunks until speech starts and then ends."""
        if not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None

        chunks = []
        pre_roll = []
        started = False
        elapsed = 0.0
        silence = 0.0

        while elapsed < max_duration:
            audio_path = self.record_from_nao(duration=chunk_duration)
            if not audio_path or not os.path.exists(audio_path):
                return None

            chunk = self._read_wav_chunk(audio_path)
            if chunk is None:
                return None

            has_speech = bool(speech_detector(audio_path))
            elapsed += chunk_duration

            if not started:
                pre_roll.append(chunk)
                pre_roll = pre_roll[-2:]
                if has_speech:
                    started = True
                    chunks.extend(pre_roll)
                    silence = 0.0
                elif elapsed >= start_timeout:
                    print("[NAOAudioTransfer] No speech detected before timeout.")
                    return None
                continue

            chunks.append(chunk)
            if has_speech:
                silence = 0.0
            else:
                silence += chunk_duration
                if silence >= silence_duration:
                    break

        if not chunks:
            return None

        self._write_wav_chunks(chunks)
        print(
            f"[NAOAudioTransfer] Speech capture complete ({elapsed:.2f}s observed)."
        )
        return self.local_path

    @staticmethod
    def _read_wav_chunk(path):
        try:
            with wave.open(path, "rb") as wav_file:
                params = wav_file.getparams()
                frames = wav_file.readframes(wav_file.getnframes())
            return params, frames
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not read audio chunk: {e}")
            return None

    def _write_wav_chunks(self, chunks):
        params = chunks[0][0]
        with wave.open(self.local_path, "wb") as wav_file:
            wav_file.setnchannels(params.nchannels)
            wav_file.setsampwidth(params.sampwidth)
            wav_file.setframerate(params.framerate)
            wav_file.writeframes(b"".join(frames for _, frames in chunks))

    def get_test_audio(self):
        """Returns the local test WAV if offline fallback is enabled."""
        if not self.use_test_audio:
            print("[NAOAudioTransfer] Test audio fallback disabled.")
            return None

        if self.test_audio_path and os.path.exists(self.test_audio_path):
            return self.test_audio_path

        print(
            f"[NAOAudioTransfer] '{self.test_audio_path}' not found. "
            "Skipping offline fallback."
        )
        return None

    def download(self):
        if not self.file_manager:
            print("[NAOAudioTransfer Warning] No ALFileManager available.")
            return None

        try:
            Path(self.local_path).parent.mkdir(parents=True, exist_ok=True)
            if os.path.exists(self.local_path):
                os.remove(self.local_path)

            self._download_with_file_manager()

            if os.path.exists(self.local_path):
                print(f"[NAOAudioTransfer] Downloaded audio to {self.local_path}")
                self.cleanup_remote_audio()
                return self.local_path

            print(
                "[NAOAudioTransfer Warning] "
                f"Transfer completed but local file was not found: {self.local_path}"
            )
            return None

        except Exception as e:
            print(f"[NAOAudioTransfer Error] Could not download NAO audio: {e}")
            return None

    def _download_with_file_manager(self):
        """
        Downloads the remote file using the dynamic qi ALFileManager proxy.

        qi service methods may not appear through hasattr(), so candidate calls
        are attempted directly and the first successful result is used.
        """
        attempts = (
            ("getFileContents", (self._remote_file_name(),)),
            ("getFileContents", (self.remote_path,)),
            ("getFile", (self.remote_path, self.local_path)),
            ("copyFileFromRobot", (self.remote_path, self.local_path)),
            ("copy", (self.remote_path, self.local_path)),
            ("getFile", (self.remote_path,)),
            ("getFileComplete", (self.remote_path,)),
        )
        errors = []

        for method_name, args in attempts:
            try:
                method = getattr(self.file_manager, method_name)
                result = method(*args)
                wrote_file = self._write_result_if_needed(result)
                if wrote_file or os.path.exists(self.local_path):
                    print(f"[NAOAudioTransfer] Transfer method used: {method_name}")
                    return

                errors.append(
                    f"{method_name}{args}: completed but did not create local file"
                )
            except Exception as e:
                errors.append(f"{method_name}{args}: {e}")

        raise RuntimeError(
            "No supported ALFileManager transfer call succeeded. "
            + " | ".join(errors)
        )

    def _get_recording_remote_path(self):
        shared_folder = self._get_user_shared_folder_path()
        if shared_folder:
            return posixpath.join(shared_folder, self._remote_file_name())
        return self.remote_path

    def _get_user_shared_folder_path(self):
        if not self.file_manager:
            return None

        try:
            shared_folder = self.file_manager.getUserSharedFolderPath()
            if shared_folder:
                return str(shared_folder).rstrip("/")
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not get shared folder: {e}")

        return None

    def _remote_file_name(self):
        return posixpath.basename(self.remote_path)

    def _write_result_if_needed(self, result):
        if result is None:
            return False

        data = None
        if isinstance(result, bytes):
            data = result
        elif isinstance(result, bytearray):
            data = bytes(result)
        elif isinstance(result, str):
            data = result.encode()
        elif isinstance(result, (list, tuple)) and result:
            payload = result[-1]
            if isinstance(payload, bytes):
                data = payload
            elif isinstance(payload, bytearray):
                data = bytes(payload)
            elif isinstance(payload, str):
                data = payload.encode()
            elif isinstance(payload, (list, tuple)):
                data = bytes(payload)

        if data is not None:
            with open(self.local_path, "wb") as audio_file:
                audio_file.write(data)
            return True

        return False

    def cleanup_remote_audio(self):
        """Removes the remote WAV from NAO after a successful download."""
        if not self.file_manager:
            return

        try:
            for method_name in ("removeFile", "deleteFile"):
                try:
                    getattr(self.file_manager, method_name)(self.remote_path)
                    print(f"[NAOAudioTransfer] Removed remote audio {self.remote_path}")
                    return
                except Exception:
                    pass
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not remove remote audio: {e}")

    def list_file_manager_methods(self):
        """Best-effort method listing for diagnostics across qi versions."""
        if not self.file_manager:
            return []

        try:
            meta_object = self.file_manager.metaObject()
            if hasattr(meta_object, "methodNames"):
                return list(meta_object.methodNames())
            if isinstance(meta_object, dict):
                methods = meta_object.get("methods") or meta_object.get("method")
                if isinstance(methods, dict):
                    return list(methods.keys())
                if isinstance(methods, list):
                    names = []
                    for method in methods:
                        if isinstance(method, dict) and "name" in method:
                            names.append(method["name"])
                        else:
                            names.append(str(method))
                    return names
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not list file methods: {e}")

        return []
