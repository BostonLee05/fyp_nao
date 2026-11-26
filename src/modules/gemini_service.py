import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

class GeminiService:
    def __init__(
        self, api_key: Optional[str] = None, system_instruction: Optional[str] = None
    ) -> None:
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.client = None
        self.chat = None
        self.last_error: Optional[str] = None

        if not self.api_key:
            print("[Gemini WARN] GEMINI_API_KEY not found.")
            self.last_error = "GEMINI_API_KEY is missing."
            return

        self.system_instruction = system_instruction or (
            "You are NAO, a friendly humanoid robot. "
            "Keep all answers very short, concise, and direct. "
            "Use simple English only. "
            "If the user speaks another language, translate it internally and respond only in English. "
            "If an image is provided, use it as the current NAO camera view when answering."
        )

        try:
            self.client = genai.Client(api_key=self.api_key)
            # Initialize a persistent chat session.
            self.chat = self.client.chats.create(
                model="gemini-3.1-flash-lite",
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=100,
                )
            )
        except Exception as e:
            self.last_error = f"Could not initialize Gemini: {e}"
            self.client = None
            self.chat = None
            print(f"[Gemini Error] {self.last_error}")

    def ask(self, prompt: str, image: Optional[bytes] = None) -> str:
        if not self.chat:
            return "Sorry, Gemini is currently unavailable."

        if not isinstance(prompt, str) or not prompt.strip():
            self.last_error = "Gemini prompt was empty."
            print(f"[Gemini Warning] {self.last_error}")
            return "Sorry, I did not receive a question."

        if image is not None and not isinstance(image, bytes):
            self.last_error = "Gemini image input was not valid bytes."
            print(f"[Gemini Warning] {self.last_error}")
            return "Sorry, the camera input was invalid."

        try:
            contents = []
            if image is not None:
                contents.append(image)
            contents.append(prompt)

            response = self.chat.send_message(contents)
            response_text = getattr(response, "text", None)
            if not isinstance(response_text, str) or not response_text.strip():
                self.last_error = "Gemini returned an empty response."
                print(f"[Gemini Warning] {self.last_error}")
                return "Sorry, Gemini returned no response."

            self.last_error = None
            return response_text.strip()
        except Exception as e:
            self.last_error = f"Gemini request failed: {e}"
            print(f"[Gemini Error] {self.last_error}")
            return "Sorry, I ran into an error trying to process that."

    def generate_sql(self, question: str, schema: List[Dict[str, Any]]) -> Optional[str]:
        """Generate one read-only query for the supplied public schema."""
        if not self.client:
            print("[Gemini SQL Warning] Gemini client is unavailable.")
            return None
        if not isinstance(question, str) or not question.strip():
            print("[Gemini SQL Warning] Cannot generate SQL for an empty question.")
            return None
        if not isinstance(schema, list):
            print("[Gemini SQL Warning] Database schema must be a list.")
            return None
        try:
            schema_lines = "\n".join(
                f"- {row['table_name']}: {row['column_name']} ({row['data_type']})"
                for row in schema
            )
        except (KeyError, TypeError) as e:
            print(f"[Gemini SQL Warning] Invalid database schema: {e}")
            return None
        prompt = (
            "Convert the classroom question into exactly one PostgreSQL SELECT query.\n"
            "Use only tables and columns in this schema. Never use INSERT, UPDATE, DELETE, "
            "DROP, ALTER, CREATE, functions with side effects, comments, or multiple statements.\n"
            "Return SQL only, with no markdown fences. If the question is not answerable from "
            "the schema, return NOT_A_DATABASE_QUESTION.\n\n"
            f"Schema:\n{schema_lines}\n\nQuestion: {question}"
        )
        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0, max_output_tokens=300),
            )
            sql = (getattr(response, "text", None) or "").strip()
            sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
            if not sql or sql.upper() == "NOT_A_DATABASE_QUESTION":
                return None
            return sql
        except Exception as e:
            print(f"[Gemini SQL Error] {e}")
            return None

    def text_to_speech(self, text: str, voice_name: str = "Puck") -> Optional[bytes]:
        """Generates audio bytes for input text using Gemini API audio modal output."""
        if not self.client:
            print("[Gemini TTS Warning] Gemini client is unavailable.")
            return None
        if not isinstance(text, str) or not text.strip():
            print("[Gemini TTS Warning] Cannot synthesize empty text.")
            return None
        if not isinstance(voice_name, str) or not voice_name.strip():
            print("[Gemini TTS Warning] Voice name is empty or invalid.")
            return None

        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    ),
                ),
            )

            # Extract generated audio bytes from response candidates
            candidates = getattr(response, "candidates", None) or []
            if not candidates or not getattr(candidates[0], "content", None):
                print("[Gemini TTS Warning] Gemini returned no audio candidates.")
                return None

            for part in getattr(candidates[0].content, "parts", None) or []:
                inline_data = getattr(part, "inline_data", None)
                audio_data = getattr(inline_data, "data", None)
                if audio_data:
                    return audio_data
            print("[Gemini TTS Warning] Gemini response contained no audio data.")
            return None
        except Exception as e:
            print(f"[Gemini TTS Error] {e}")
            return None
