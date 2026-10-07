"""Quick offline sanity test of the deterministic pipeline (no LLM/TTS keys needed)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
# force fallback (no LLM) for a fast deterministic check
os.environ.pop("EMERGENT_LLM_KEY", None)

from cs2.pipeline import run_pipeline
from cs2.datasource import SyntheticDataSource


async def main():
    res = await run_pipeline(SyntheticDataSource(), "/tmp/cs2_test_out")
    print("Map:", res["map"])
    print("Score CT/T:", res["score"])
    print("Rounds:", res["total_rounds"], "Kills:", res["total_kills"])
    print("Candidate highlights:", res["total_candidate_highlights"])
    print("Commentary events:", res["total_commentary_events"])
    print("Hype distribution:", res["hype_distribution"])
    print("Clutches:", [(s["player"], s["clutch"]["starting_situation"]) for s in res["clutches"]])
    print("Multikills:", [(s["player"], s["kills"]) for s in res["multikills"]])
    print("--- sample commentary ---")
    for c in res["commentary"][:6]:
        print(f'  [L{c["hype_level"]}] R{c["round"]} {c["text"]}')


if __name__ == "__main__":
    asyncio.run(main())
