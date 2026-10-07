"""Validate TTS: ElevenLabs -> OpenAI fallback composite generates one clip."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from cs2.config import get_config
from cs2.tts_client import get_tts_provider


async def main():
    tts = get_tts_provider(get_config())
    print("available:", tts.available())
    ok = await tts.generate("One versus three, and he clutches it! What a round!", "/tmp/cs2_tts_test.mp3")
    print("generated:", ok, "size:", os.path.getsize("/tmp/cs2_tts_test.mp3") if ok else 0)


asyncio.run(main())
