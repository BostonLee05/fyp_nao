import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

class GeminiService(object):
    def __init__(self, api_key=None, system_instruction=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            print("[Gemini WARN] GEMINI_API_KEY not found.")
            self.client = None
            self.chat = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            self.system_instruction = system_instruction or (
                "You are NAO, a friendly humanoid robot. "
                "Keep all answers very short, concise, and direct (1 to 2 sentences maximum). "
                "Use simple language suitable for a general class audience with a natural tone."
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

    def ask(self, prompt, image=None):
        if not self.chat:
            return "My Gemini API key is missing."

        try:
            contents = []
            if image is not None:
                contents.append(image)
                if isinstance(image, bytes):
                    contents.append(
                        types.Part.from_bytes(
                            data=image,
                            mime_type="image/jpeg",
                        )
                    )
                else:
                    contents.append(image)
            contents.append(prompt)

            response = self.chat.send_message(contents)
            return response.text.strip()
        except Exception as e:
            print(f"[Gemini Error] {e}")
            return "Sorry, I ran into an error trying to process that."

    def text_to_speech(self, text, voice_name="Puck"):
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

