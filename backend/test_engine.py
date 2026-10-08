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
    print("candidates", stats["candidates"], "commentary", len(timeline), "LLM_calls", llm_calls)
    print("hype levels:", {l: sum(1 for c in timeline if c.hype_level == l) for l in range(6)})
    print("\n--- chronological commentary (first ~2 rounds) ---")
    rounds_seen = set()
    for c in timeline:
        rounds_seen.add(c.round)
        if len(rounds_seen) > 2:
            break
        print(f"  R{c.round} {int(c.demo_time//60):02d}:{c.demo_time%60:05.2f} "
              f"[L{c.hype_level} {c.method} p={c.priority}] {c.text}")
    print("\n--- all clutch / ace lines ---")
    for c in timeline:
        if c.event_type in ("CLUTCH", "CLUTCH_WIN") or "ACE" in c.text.upper():
            print(f"  R{c.round} [{c.event_type} L{c.hype_level} {c.method}] {c.text}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
