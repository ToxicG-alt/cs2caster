"""TTS provider abstraction. ElevenLabs first; graceful no-op when no key.
The pipeline still produces commentary.json + report without audio."""
import logging
import os

log = logging.getLogger("cs2.tts")


class TTSProvider:
    def available(self) -> bool:
        return False

    def generate(self, text: str, out_path: str) -> bool:
        raise NotImplementedError


class ElevenLabsProvider(TTSProvider):
    def __init__(self, cfg):
        self.cfg = cfg
        self.key = os.environ.get("ELEVENLABS_API_KEY")
        self.voice_id = cfg["tts"]["voice_id"]
        self.model_id = cfg["tts"]["model_id"]

    def available(self):
        return bool(self.key)

    def generate(self, text, out_path):
        if not self.key:
            return False
        try:
            from elevenlabs import ElevenLabs, VoiceSettings
            client = ElevenLabs(api_key=self.key)
            audio = client.text_to_speech.convert(
                text=text, voice_id=self.voice_id, model_id=self.model_id,
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(stability=0.4, similarity_boost=0.8,
                                             style=0.6, use_speaker_boost=True),
            )
            data = b"".join(audio)
            with open(out_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:  # noqa
            log.warning("ElevenLabs TTS failed: %s", e)
            return False


def get_tts_provider(cfg):
    return ElevenLabsProvider(cfg)
