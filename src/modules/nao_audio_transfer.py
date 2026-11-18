import os
import posixpath
import time
import uuid
import wave
from pathlib import Path
import threading

class NAOAudioTransfer:
    """Handles NAO audio capture, download, and local test-audio fallback."""

    def __init__(
        self,
        audio_recorder=None,
        file_manager=None,
        remote_path="/home/nao/nao_speech.wav",
        local_path=None,
    ):
        self.audio_recorder = audio_recorder
        self.file_manager = file_manager
        self.remote_path = remote_path
        self.local_path = local_path
        self.recording_lock = threading.Lock()
        self.last_metrics = {}
        self.recording_id = None

    def record_from_nao(self, duration, log_performance=True):
        """Records audio on NAO and downloads it to the local machine."""
        if not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None
        if not self.recording_lock.acquire(blocking=False):
            print("[NAOAudioTransfer Warning] Recording already in progress.")
            return None

        recording_started_at = time.perf_counter()
        recording_started_wall = time.time()
        self.recording_id = "nao-" + uuid.uuid4().hex
        try:
            self.remote_path = self._get_recording_remote_path()
            if self.local_path:
                local_dir = os.path.dirname(self.local_path) or "."
                self.local_path = os.path.join(
                    local_dir,
                    "%s.wav" % self.recording_id,
                )
            print(
                "[NAOAudioTransfer] Recording id=%s on NAO: %s"
                % (self.recording_id, self.remote_path)
            )
            self.audio_recorder.startMicrophonesRecording(
                self.remote_path, "wav", 16000, [1, 1, 1, 1]
            )

            print(
                "[NAOAudioTransfer] Recording for %.1f seconds..."
                % float(duration)
            )
            time.sleep(max(0.1, float(duration)))

            try:
                self.audio_recorder.stopMicrophonesRecording()
            except Exception as stop_error:
                print(
                    "[NAOAudioTransfer Warning] stopMicrophonesRecording failed: %s"
                    % stop_error
                )

            recording_completed_at = time.perf_counter()
            self.last_metrics.update({
                "recording_id": self.recording_id,
                "recording_start_wall": recording_started_wall,
                "recording_seconds": recording_completed_at - recording_started_at,
            })
            print(
                "[NAOAudioTransfer] Recording complete in %.3fs"
                % (recording_completed_at - recording_started_at)
            )

            return self.download(
                log_performance=log_performance,
                recording_completed_at=recording_completed_at,
            )
        except Exception as e:
            print("[NAOAudioTransfer Error] Failed to record from NAO: %s" % e)
            return None
        finally:
            self.recording_lock.release()
            if log_performance:
                print(
                    "[Performance] Audio recording: %.3fs"
                    % (time.perf_counter() - recording_started_at)
                )

    def download(self, log_performance=True, recording_completed_at=None):
        transfer_started_at = time.perf_counter()
        transfer_started_wall = time.time()
        self.last_metrics.update({
            "transfer_start_wall": transfer_started_wall,
        })
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
            temp_path = self.local_path + ".transfer-" + uuid.uuid4().hex + ".tmp"
            original_local_path = self.local_path
            self.local_path = temp_path
            try:
                self._download_with_file_manager()
            finally:
                self.local_path = original_local_path

            if os.path.exists(temp_path):
                integrity = self.validate_wav(temp_path)
                if not integrity["valid"]:
                    os.remove(temp_path)
                    print(
                        "[NAOAudioTransfer Warning] Invalid WAV transfer: %s"
                        % integrity["error"]
                    )
                    return None

                os.replace(temp_path, self.local_path)
                transfer_completed_at = time.perf_counter()
                self.last_metrics.update({
                    "transfer_seconds": transfer_completed_at - transfer_started_at,
                    "transfer_completion_wall": time.time(),
                    "transfer_bytes": integrity["bytes"],
                    "recording_completed_to_transfer_complete_seconds":
                        (
                            transfer_completed_at - recording_completed_at
                            if recording_completed_at is not None
                            else None
                        ),
                })
                print(
                    "[NAOAudioTransfer] Downloaded and validated recording id=%s"
                    " (%d bytes, %.3fs)"
                    % (
                        self.recording_id,
                        integrity["bytes"],
                        self.last_metrics["transfer_seconds"],
                    )
                )
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
        remote_dir = posixpath.dirname(self.remote_path) or "/home/nao"
        return posixpath.join(remote_dir, self._remote_file_name())

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
        if getattr(self, "recording_id", None):
            return "%s.wav" % self.recording_id
        return posixpath.basename(self.remote_path)

    def validate_wav(self, path):
        """Checks basic WAV structure, size, duration, and expected format."""
        result = {"valid": False, "error": "", "bytes": 0}
        try:
            size = os.path.getsize(path)
            result["bytes"] = size
            if size < 44:
                result["error"] = "file is smaller than a WAV header"
                return result

            with wave.open(path, "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_rate = wav_file.getframerate()
                sample_width = wav_file.getsampwidth()
                frame_count = wav_file.getnframes()
                if channels != 1:
                    result["error"] = "expected mono WAV; found %d channels" % channels
                    return result
                if sample_rate != 16000:
                    result["error"] = "expected 16000 Hz; found %d Hz" % sample_rate
                    return result
                if sample_width != 2:
                    result["error"] = "expected 16-bit PCM; found %d bytes" % sample_width
                    return result
                if frame_count < 160:
                    result["error"] = "WAV contains less than 10 ms of audio"
                    return result

                duration = frame_count / float(sample_rate)
                result["duration_seconds"] = duration
                result["valid"] = True
                result["channels"] = channels
                result["sample_rate"] = sample_rate
                result["sample_width"] = sample_width
                return result
        except Exception as error:
            result["error"] = str(error)
            return result

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