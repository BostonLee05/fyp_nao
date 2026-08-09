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
            contents.append(prompt)

            # send_message supports passing lists containing PIL Images + text
            response = self.chat.send_message(contents)
            return response.text.strip()
        except Exception as e:
            print(f"[Gemini Error] {e}")
            return "Sorry, I ran into an error trying to process that."