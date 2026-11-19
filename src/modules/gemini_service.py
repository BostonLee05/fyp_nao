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
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            print("[Gemini WARN] GEMINI_API_KEY not found.")
            self.client = None
            self.chat = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            self.system_instruction = system_instruction or (
                "You are NAO, a friendly humanoid robot. "
                "Keep all answers very short, concise, and direct. "
                "Use simple English only. "
                "If the user speaks another language, translate it internally and respond only in English. "
                "If an image is provided, use it as the current NAO camera view when answering."
            )
            # Initialize a persistent chat session
            self.chat = self.client.chats.create(
                model="gemini-3.1-flash-lite",
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=100,
                )
            )

    def ask(self, prompt: str, image: Optional[bytes] = None) -> str:
        if not self.chat:
            return "My Gemini API key is missing."

        try:
            contents = []
            if image is not None:
                if isinstance(image, bytes):
                     contents.append(image)
            contents.append(prompt)

            response = self.chat.send_message(contents)
            return response.text.strip()
        except Exception as e:
            print(f"[Gemini Error] {e}")
            return "Sorry, I ran into an error trying to process that."

    def generate_sql(self, question: str, schema: List[Dict[str, Any]]) -> Optional[str]:
        """Generate one read-only query for the supplied public schema."""
        if not self.client:
            return None
        schema_lines = "\n".join(
            f"- {row['table_name']}: {row['column_name']} ({row['data_type']})"
            for row in schema
        )
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
            sql = (response.text or "").strip()
            sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql, flags=re.IGNORECASE).strip()
            if sql.upper() == "NOT_A_DATABASE_QUESTION":
                return None
            return sql
        except Exception as e:
            print(f"[Gemini SQL Error] {e}")
            return None

    def text_to_speech(self, text: str, voice_name: str = "Puck") -> Optional[bytes]:
        """Generates audio bytes for input text using Gemini API audio modal output."""
        if not self.client:
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
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return part.inline_data.data
            return None
        except Exception as e:
            print(f"[Gemini TTS Error] {e}")
            return None
