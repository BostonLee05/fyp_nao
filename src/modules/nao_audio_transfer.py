import os
import posixpath
import time
import wave
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

class NAOAudioTransfer:
    """Handles NAO audio capture, download, and local test-audio fallback."""

    def __init__(
        self,
        audio_recorder: Optional[Any] = None,
        file_manager: Optional[Any] = None,
        remote_path: str = "/home/nao/nao_speech.wav",
        local_path: Optional[str] = None,
    ) -> None:
        self.audio_recorder = audio_recorder
        self.file_manager = file_manager
        self.remote_path = remote_path
        self.local_path = local_path
        self.stop_event = threading.Event()

    def stop(self) -> None:
        """Cancel an active capture and stop the NAO recorder best-effort."""
        self.stop_event.set()
        self._stop_recording_if_active()

    def record_from_nao(self, duration: float, log_performance: bool = True) -> Optional[str]:
        """Records audio on NAO and downloads it to the local machine."""
        if self.stop_event.is_set() or not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None

        recording_started_at = time.perf_counter()
        recording_active = False
        try:
            self.remote_path = self._get_recording_remote_path()
            print(f"[NAOAudioTransfer] Recording on NAO: {self.remote_path}")

            # ALSpeechRecognition and ALAudioRecorder share NAO's microphone.
            # Unsubscribing speech recognition may not release it immediately,
            # so stop any stale recording before starting this one.
            self._stop_recording_if_active()
            try:
                audio_recording_started_at = time.perf_counter()
                self.audio_recorder.startMicrophonesRecording(
                    self.remote_path, "wav", 16000, [1, 1, 1, 1]
                )
            except Exception as first_error:
                if "Already recording" not in str(first_error):
                    raise

                print(
                    "[NAOAudioTransfer Warning] NAO recorder was already active; "
                    "stopping it and retrying."
                )
                self._stop_recording_if_active()
                time.sleep(0.2)
                self.audio_recorder.startMicrophonesRecording(
                    self.remote_path, "wav", 16000, [1, 1, 1, 1]
                )
            recording_active = True

            print(f"[NAOAudioTransfer] Recording for {duration} seconds...")
            deadline = time.monotonic() + max(0.0, float(duration))
            while not self.stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.stop_event.wait(min(0.1, remaining))

            if self.stop_event.is_set():
                return None

            self.audio_recorder.stopMicrophonesRecording()
            recording_active = False
            print(
                f"[Performance] Audio recording (NAO): "
                f"{time.perf_counter() - audio_recording_started_at:.3f}s"
            )
            print("[NAOAudioTransfer] NAO recording stopped.")

            return self.download(log_performance=log_performance)
        except Exception as e:
            print(f"[NAOAudioTransfer Error] Failed to record from NAO: {e}")
            return None
        finally:
            if recording_active:
                self._stop_recording_if_active()
            if log_performance:
                print(
                    f"[Performance] Audio recording + transfer pipeline: "
                    f"{time.perf_counter() - recording_started_at:.3f}s"
                )

    def _stop_recording_if_active(self) -> None:
        """Best-effort cleanup for a recorder left active by another service."""
        try:
            self.audio_recorder.stopMicrophonesRecording()
            print("[NAOAudioTransfer] Stopped existing NAO recording.")
        except Exception:
            # NAO raises when no recording is active; that is harmless here.
            pass

    def record_until_silence(
        self,
        speech_detector: Callable[[str], bool],
        chunk_duration: float = 0.25,
        start_timeout: float = 8,
        silence_duration: float = 0.75,
        max_duration: float = 20,
    ) -> Optional[str]:
        """Capture short NAO chunks until speech ends or the safety limit hits."""
        if not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None

        chunks = []
        capture_started_at = time.perf_counter()
        pre_roll = []
        started = False
        elapsed = 0.0
        silence = 0.0

        while elapsed < max_duration:
            audio_path = self.record_from_nao(
                duration=chunk_duration,
                log_performance=False,
            )
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
        print(
            f"[Performance] Audio recording and transfer (speech-end capture): "
            f"{time.perf_counter() - capture_started_at:.3f}s"
        )
        return self.local_path

    @staticmethod
    def _read_wav_chunk(path: str) -> Optional[Tuple[Any, bytes]]:
        try:
            with wave.open(path, "rb") as wav_file:
                params = wav_file.getparams()
                frames = wav_file.readframes(wav_file.getnframes())
            return params, frames
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not read audio chunk: {e}")
            return None

    def _write_wav_chunks(self, chunks: List[Tuple[Any, bytes]]) -> None:
        params = chunks[0][0]
        with wave.open(self.local_path, "wb") as wav_file:
            wav_file.setnchannels(params.nchannels)
            wav_file.setsampwidth(params.sampwidth)
            wav_file.setframerate(params.framerate)
            wav_file.writeframes(b"".join(frames for _, frames in chunks))

    def download(self, log_performance: bool = True) -> Optional[str]:
        transfer_started_at = time.perf_counter()
        if not self.file_manager:
            print("[NAOAudioTransfer Warning] No ALFileManager available.")
            if log_performance:
                print(
                    f"[Performance] Audio transfer: "
                    f"{time.perf_counter() - transfer_started_at:.3f}s"
                )
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
        finally:
            if log_performance:
                print(
                    f"[Performance] Audio transfer: "
                    f"{time.perf_counter() - transfer_started_at:.3f}s"
                )

    def _download_with_file_manager(self) -> None:
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

    def _get_recording_remote_path(self) -> str:
        shared_folder = self._get_user_shared_folder_path()
        if shared_folder:
            return posixpath.join(shared_folder, self._remote_file_name())
        return self.remote_path

    def _get_user_shared_folder_path(self) -> Optional[str]:
        if not self.file_manager:
            return None

        try:
            shared_folder = self.file_manager.getUserSharedFolderPath()
            if shared_folder:
                return str(shared_folder).rstrip("/")
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not get shared folder: {e}")

        return None

    def _remote_file_name(self) -> str:
        return posixpath.basename(self.remote_path)

    def _write_result_if_needed(self, result: Any) -> bool:
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

    def cleanup_remote_audio(self) -> None:
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

    def list_file_manager_methods(self) -> List[str]:
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
