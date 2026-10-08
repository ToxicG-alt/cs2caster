"""TTS provider abstraction (async). ElevenLabs preferred; automatic OpenAI
fallback via the Emergent key (works from cloud). Graceful no-op if neither works.
The pipeline still produces commentary.json + report without audio."""
import asyncio
import logging
import os

log = logging.getLogger("cs2.tts")


class TTSProvider:
    def available(self) -> bool:
        return False

    async def generate(self, text: str, out_path: str) -> bool:
        raise NotImplementedError


class ElevenLabsProvider(TTSProvider):
    def __init__(self, cfg):
        self.key = os.environ.get("ELEVENLABS_API_KEY")
        self.voice_id = cfg["tts"]["voice_id"]
        self.model_id = cfg["tts"]["model_id"]

    def available(self):
        return bool(self.key)

    def _sync_generate(self, text, out_path):
        import wave
        from elevenlabs import ElevenLabs, VoiceSettings
        client = ElevenLabs(api_key=self.key)
        audio = client.text_to_speech.convert(
            text=text, voice_id=self.voice_id, model_id=self.model_id,
            output_format="pcm_44100",
            voice_settings=VoiceSettings(stability=0.4, similarity_boost=0.8,
                                         style=0.6, use_speaker_boost=True),
        )
        pcm = b"".join(audio)
        w = wave.open(out_path, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(pcm)
        w.close()
        return True

    async def generate(self, text, out_path):
        if not self.key:
            return False
        try:
            return await asyncio.to_thread(self._sync_generate, text, out_path)
        except Exception as e:  # noqa
            log.warning("ElevenLabs TTS failed (%s)", str(e)[:120])
            return False


class OpenAITTSProvider(TTSProvider):
    def __init__(self, cfg):
        self.key = os.environ.get("EMERGENT_LLM_KEY")
        self.voice = cfg["tts"].get("openai_voice", "onyx")
        self.model = cfg["tts"].get("openai_model", "tts-1-hd")

    def available(self):
        return bool(self.key)

    async def generate(self, text, out_path):
        if not self.key:
            return False
        try:
            from emergentintegrations.llm.openai import OpenAITextToSpeech
            tts = OpenAITextToSpeech(api_key=self.key)
            audio = await tts.generate_speech(text=text, model=self.model,
                                              voice=self.voice, response_format="wav")
            with open(out_path, "wb") as f:
                f.write(audio)
            return True
        except Exception as e:  # noqa
            log.warning("OpenAI TTS failed (%s)", str(e)[:120])
            return False


class CompositeTTSProvider(TTSProvider):
    """Try ElevenLabs first (preferred caster voice), fall back to OpenAI."""
    def __init__(self, cfg):
        self.primary = ElevenLabsProvider(cfg)
        self.fallback = OpenAITTSProvider(cfg)
        self._primary_dead = False

    def available(self):
        return self.primary.available() or self.fallback.available()

    async def generate(self, text, out_path):
        if self.primary.available() and not self._primary_dead:
            if await self.primary.generate(text, out_path):
                return True
            self._primary_dead = True  # stop hammering a blocked account
            log.warning("ElevenLabs unavailable; switching to OpenAI TTS fallback")
        return await self.fallback.generate(text, out_path)


def get_tts_provider(cfg):
    return CompositeTTSProvider(cfg)
