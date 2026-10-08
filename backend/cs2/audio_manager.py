"""Stitch per-line TTS clips into one match-length WAV, each placed at its demo timestamp,
so the file plays in sync with the recorded demo. Pure stdlib (no ffmpeg needed)."""
import logging
import wave

log = logging.getLogger("cs2.audio")


def build_timeline_wav(clips, out_path):
    """clips = [(demo_time_seconds, wav_path), ...]. Returns True on success."""
    segs = []
    params = None
    for t, p in clips:
        if not p:
            continue
        try:
            w = wave.open(p, "rb")
            if params is None:
                params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            frames = w.readframes(w.getnframes())
            w.close()
            segs.append((t, frames))
        except Exception as e:  # noqa
            log.warning("skip clip %s: %s", p, e)
    if not segs or params is None:
        return False
    nch, sw, fr = params
    bpf = nch * sw
    total_t = max(t + len(f) / bpf / fr for t, f in segs) + 0.5
    buf = bytearray(int(total_t * fr) * bpf)
    for t, f in segs:
        off = int(t * fr) * bpf
        end = min(off + len(f), len(buf))
        buf[off:end] = f[:end - off]
    out = wave.open(out_path, "wb")
    out.setnchannels(nch)
    out.setsampwidth(sw)
    out.setframerate(fr)
    out.writeframes(bytes(buf))
    out.close()
    return True
