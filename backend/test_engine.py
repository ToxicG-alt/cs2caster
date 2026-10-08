"""Event-synchronized engine test on a real .dem (deterministic, no LLM/TTS)."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
os.environ.pop("ELEVENLABS_API_KEY", None)  # skip TTS here
from cs2.config import get_config
from cs2.datasource import DemoDataSource
from cs2.commentary_engine import CommentaryEngine
from cs2.llm_client import get_llm_provider


async def main(path):
    cfg = get_config()
    src = DemoDataSource(path)
    info = src.get_match_info()
    events = src.get_events()
    print("MAP", info.map, "events", len(events))
    eng = CommentaryEngine(info, events, cfg, get_llm_provider(cfg))
    timeline, debug, llm_calls, stats = await eng.run()
    print("score", stats["score"], "rounds", stats["total_rounds"], "kills", stats["total_kills"])
    print("candidates", stats["candidates"], "commentary", len(timeline), "LLM_calls", llm_calls,
          "analyst_llm", eng.analyst_llm_calls)
    modes = {}
    for c in timeline:
        m = ("analysis" if c.event_type == "ANALYSIS" else "filler" if c.event_type == "FILLER" else "play")
        modes[m] = modes.get(m, 0) + 1
    print("modes:", modes)
    print("\n--- TRANSCRIPT (first ~3 rounds) ---")
    seen = set()
    for c in timeline:
        seen.add(c.round)
        if len(seen) > 3:
            break
        tag = ("PLAY" if c.event_type not in ("ANALYSIS", "FILLER") else c.event_type)
        print(f"  {int(c.demo_time//60):02d}:{c.demo_time%60:05.2f} [{tag} L{c.hype_level} {c.method}] {c.text}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
