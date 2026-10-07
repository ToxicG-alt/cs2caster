"""Orchestrates the full pipeline:
demo -> events -> game state -> highlights -> clustering -> match memory ->
LLM analyst -> caster -> TTS -> commentary.json + match_report.txt + audio."""
import asyncio
import json
import logging
import os
from collections import Counter
from pathlib import Path

from .config import get_config
from .datasource import DemoDataSource, SyntheticDataSource
from .detection import cluster_situations, detect_round_highlights
from .game_state import build_match_state
from .llm_client import get_llm_provider
from .match_memory import MatchMemory
from .tts_client import get_tts_provider

log = logging.getLogger("cs2.pipeline")


async def run_pipeline(source, out_dir, cfg=None, progress=None):
    cfg = cfg or get_config()
    out = Path(out_dir)
    (out / "audio").mkdir(parents=True, exist_ok=True)

    def emit(stage, pct):
        log.info("[%s] %s%%", stage, pct)
        if progress:
            progress(stage, pct)

    emit("parsing_demo", 5)
    info = source.get_match_info()
    events = source.get_events()
    emit("building_game_state", 20)
    match = build_match_state(info, events)

    emit("detecting_highlights", 35)
    situations = detect_round_highlights(match, cfg)
    situations = cluster_situations(situations, cfg)

    emit("building_match_memory", 45)
    memory = MatchMemory(match)
    memory.ingest(match, situations)

    # pick top-N for AI commentary (cost control)
    max_n = cfg["commentary"]["max_situations"]
    comment_min = cfg["commentary"]["comment_min_hype"]
    candidates = [s for s in situations if s["hype_level"] >= comment_min][:max_n]

    llm = get_llm_provider(cfg)
    tts = get_tts_provider(cfg)

    emit("ai_analysis_and_commentary", 55)
    commentary = []
    debug_log = []
    for i, s in enumerate(candidates):
        s["memory"] = memory.context_for(s)
        analyst = await llm.analyze(s)
        if not analyst.get("should_comment", True):
            continue
        line = await llm.cast(analyst, s)
        entry = {
            "timestamp": round(s["end_ts"], 2),
            "round": s["round"],
            "hype_level": analyst.get("hype_level", s["hype_level"]),
            "importance": analyst.get("importance", min(100, s["hype_score"] * 3)),
            "situation": s["situation_type"],
            "player": s["player"],
            "text": line,
            "facts_used": analyst.get("facts", s["reasons"]),
            "confidence": analyst.get("confidence", s["confidence"].lower()),
            "audio": None,
        }
        commentary.append(entry)
        debug_log.append(_debug_block(s, analyst, line))
        pct = 55 + int(35 * (i + 1) / max(1, len(candidates)))
        emit("ai_analysis_and_commentary", min(90, pct))

    commentary.sort(key=lambda c: c["timestamp"])

    emit("tts", 92)
    tts_ok = tts.available()
    if tts_ok:
        for idx, c in enumerate(commentary):
            fname = f"audio/clip_{idx:03d}.mp3"
            if tts.generate(c["text"], str(out / fname)):
                c["audio"] = fname

    emit("writing_outputs", 97)
    result = _assemble_result(info, match, situations, commentary, memory, cfg, tts_ok)
    with open(out / "commentary.json", "w") as f:
        json.dump(commentary, f, indent=2)
    with open(out / "match_report.txt", "w") as f:
        f.write(_match_report(result, debug_log))
    with open(out / "result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    emit("done", 100)
    return result


def _debug_block(s, analyst, line):
    return {
        "round": s["round"], "player": s["player"], "situation": s["situation_type"],
        "min_hp": s["min_hp"], "weapons": s["weapons"], "gaps_s": s["gaps_s"],
        "hype_score": s["hype_score"], "hype_level": s["hype_level"],
        "reasons": s["reasons"], "decision": "COMMENT" if analyst.get("should_comment") else "SILENT",
        "commentary": line,
    }


def _assemble_result(info, match, situations, commentary, memory, cfg, tts_ok):
    hype_dist = Counter(s["hype_level"] for s in situations)
    top = sorted(situations, key=lambda s: s["hype_score"], reverse=True)[:10]
    clutches = [s for s in situations if s.get("clutch")]
    multikills = [s for s in situations if s["kills"] >= 3]
    return {
        "map": info.map,
        "team_ct": info.team_ct, "team_t": info.team_t,
        "players": info.players,
        "score": {"ct": match.ct_score, "t": match.t_score},
        "total_rounds": len(match.rounds),
        "total_kills": sum(len(r.kills) for r in match.rounds),
        "total_candidate_highlights": len(situations),
        "total_commentary_events": len(commentary),
        "hype_distribution": {str(k): hype_dist.get(k, 0) for k in range(6)},
        "player_stats": memory.stats(),
        "top_highlights": top,
        "clutches": clutches,
        "multikills": multikills,
        "commentary": commentary,
        "tts_available": tts_ok,
        "caster": cfg["caster"]["name"],
    }


def _match_report(r, debug_log):
    L = []
    L.append("=" * 60)
    L.append("CS2 AI CASTER — MATCH REPORT")
    L.append("=" * 60)
    L.append(f"Map: {r['map']}")
    L.append(f"Teams: {r['team_ct']} (CT)  vs  {r['team_t']} (T)")
    L.append(f"Final score — CT {r['score']['ct']} : {r['score']['t']} T")
    L.append(f"Rounds: {r['total_rounds']}   Kills: {r['total_kills']}")
    L.append("")
    L.append("PLAYER STATS (kills / deaths):")
    ks = r["player_stats"]["kills"]
    ds = r["player_stats"]["deaths"]
    for p in sorted(ks, key=lambda x: ks[x], reverse=True):
        L.append(f"  {p:<16} {ks.get(p,0)}K / {ds.get(p,0)}D")
    L.append("")
    L.append("QUALITY CONTROL — hype distribution:")
    for lvl in range(6):
        L.append(f"  Level {lvl}: {r['hype_distribution'].get(str(lvl),0)}")
    L.append(f"  Candidate highlights: {r['total_candidate_highlights']}")
    L.append(f"  Commentary events:    {r['total_commentary_events']}")
    L.append("")
    L.append("CLUTCHES:")
    for s in r["clutches"]:
        c = s["clutch"]
        L.append(f"  R{s['round']} {s['player']} {c['starting_situation']} "
                 f"({c['kills']} kills, {c['hp_start']}HP, {'WON' if c['round_won'] else 'lost'})")
    if not r["clutches"]:
        L.append("  (none)")
    L.append("")
    L.append("MULTI-KILLS:")
    for s in r["multikills"]:
        L.append(f"  R{s['round']} {s['player']} {s['kills']}K ({s['sequence_duration']}s)")
    if not r["multikills"]:
        L.append("  (none)")
    L.append("")
    L.append("=" * 60)
    L.append("DEBUG — DETECTED HIGHLIGHTS & COMMENTARY")
    L.append("=" * 60)
    for d in debug_log:
        L.append("")
        L.append(f"Round {d['round']} | {d['player']} | {d['situation']}")
        L.append(f"  HP(min): {d['min_hp']}  Weapons: {d['weapons']}  Gaps: {d['gaps_s']}")
        L.append(f"  Hype score: {d['hype_score']}  Level: {d['hype_level']}")
        L.append(f"  Reasons: {', '.join(d['reasons'])}")
        L.append(f"  Decision: {d['decision']}")
        L.append(f'  Commentary: "{d["commentary"]}"')
    return "\n".join(L)


def make_source(path=None, tickrate=64):
    if path and os.path.exists(path):
        return DemoDataSource(path, tickrate=tickrate)
    return SyntheticDataSource(tickrate=tickrate)
