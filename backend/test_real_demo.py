"""Parse a real .dem end-to-end (deterministic only; no LLM/TTS)."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.pop("EMERGENT_LLM_KEY", None)
os.environ.pop("ELEVENLABS_API_KEY", None)
from cs2.datasource import DemoDataSource
from cs2.pipeline import run_pipeline


async def main(path):
    src = DemoDataSource(path)
    info = src.get_match_info()
    print("MAP:", info.map, "| players:", len(info.players), "->", info.players[:12])
    res = await run_pipeline(src, "/tmp/cs2_real_out")
    print("score CT/T:", res["score"], "| rounds:", res["total_rounds"], "| kills:", res["total_kills"])
    print("candidate highlights:", res["total_candidate_highlights"])
    print("hype dist:", res["hype_distribution"])
    print("clutches:", [(s["player"], s["clutch"]["starting_situation"], s["clutch"]["round_won"]) for s in res["clutches"]][:8])
    print("multikills:", [(s["player"], s["kills"]) for s in res["multikills"]][:8])
    print("top5:")
    for s in res["top_highlights"][:5]:
        print(f"  R{s['round']} {s['player']} {s['situation_type']} score={s['hype_score']} L{s['hype_level']} hp={s['min_hp']} w={s['weapons'][:3]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
