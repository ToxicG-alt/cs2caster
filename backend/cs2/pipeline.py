"""Orchestrates the event-driven pipeline:
demo -> chronological GameEvent stream -> CommentaryEngine (deterministic detect + score +
templates, rare LLM) -> TTS -> commentary.json + match_report.txt + audio.
Commentary is generated in demo-time order and NEVER uses future events."""
import asyncio
import json
import logging
import os
from collections import Counter
from pathlib import Path

from .config import get_config
from .datasource import DemoDataSource, SyntheticDataSource
from .commentary_engine import CommentaryEngine
from .llm_client import get_llm_provider
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

    emit("chronological_commentary", 30)
    llm = get_llm_provider(cfg)
    engine = CommentaryEngine(info, events, cfg, llm)
    timeline, debug_lines, llm_calls, stats = await engine.run(
        progress=lambda p: emit("chronological_commentary", 30 + int(0.55 * p)))

    commentary = []
    for ev in timeline:
        mode = ("analysis" if ev.event_type == "ANALYSIS"
                else "filler" if ev.event_type == "FILLER" else "play")
        commentary.append({
            "timestamp": round(ev.demo_time, 2), "round": ev.round,
            "hype_level": ev.hype_level, "importance": min(100, ev.priority),
            "situation": ev.reason, "player": ev.player, "text": ev.text,
            "facts_used": ev.facts, "confidence": "high", "method": ev.method,
            "mode": mode, "duration": ev.duration, "audio": None,
        })

    tts = get_tts_provider(cfg)
    emit("tts", 88)
    tts_ok = tts.available()
    clips = []
    if tts_ok:
        any_audio = False
        for idx, c in enumerate(commentary):
            fname = f"audio/clip_{idx:03d}.wav"
            fpath = str(out / fname)
            if await tts.generate(c["text"], fpath):
                c["audio"] = fname
                clips.append((c["timestamp"], fpath))
                any_audio = True
        tts_ok = any_audio
    full_audio = False
    if clips:
        from .audio_manager import build_timeline_wav
        full_audio = build_timeline_wav(clips, str(out / "caster_audio.wav"))

    emit("writing_outputs", 97)
    result = _assemble_result(info, stats, commentary, llm_calls, cfg, tts_ok, full_audio)
    with open(out / "commentary.json", "w") as f:
        json.dump(commentary, f, indent=2)
    with open(out / "match_report.txt", "w") as f:
        f.write(_match_report(result, debug_lines))
    with open(out / "result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    emit("done", 100)
    return result


def _assemble_result(info, stats, commentary, llm_calls, cfg, tts_ok, full_audio=False):
    hype_dist = Counter(c["hype_level"] for c in commentary)
    modes = Counter(c["mode"] for c in commentary)
    return {
        "map": info.map,
        "team_ct": info.team_ct, "team_t": info.team_t,
        "players": info.players,
        "score": stats["score"],
        "total_rounds": stats["total_rounds"],
        "total_kills": stats["total_kills"],
        "total_candidate_highlights": stats["candidates"],
        "total_commentary_events": len(commentary),
        "llm_calls": llm_calls,
        "hype_distribution": {str(k): hype_dist.get(k, 0) for k in range(6)},
        "player_stats": stats["player_stats"],
        "top_highlights": stats["top_highlights"],
        "clutches": stats["clutches"],
        "multikills": stats["multikills"],
        "commentary": commentary,
        "tts_available": tts_ok,
        "full_audio": full_audio,
        "mode_distribution": dict(modes),
        "caster": cfg["caster"]["name"],
    }


def _match_report(r, debug_lines):
    L = ["=" * 60, "CS2 AI CASTER — MATCH REPORT (event-synchronized)", "=" * 60]
    L.append(f"Map: {r['map']}")
    L.append(f"Final score — CT {r['score']['ct']} : {r['score']['t']} T")
    L.append(f"Rounds: {r['total_rounds']}   Kills: {r['total_kills']}")
    L.append(f"LLM calls this match: {r['llm_calls']}   Commentary lines: {r['total_commentary_events']}")
    L.append("")
    L.append("PLAYER STATS (kills / deaths):")
    ks, ds = r["player_stats"]["kills"], r["player_stats"]["deaths"]
    for p in sorted(ks, key=lambda x: ks[x], reverse=True):
        L.append(f"  {p:<18} {ks.get(p,0)}K / {ds.get(p,0)}D")
    L.append("")
    L.append("QUALITY CONTROL — hype distribution (commentary lines):")
    for lvl in range(6):
        L.append(f"  Level {lvl}: {r['hype_distribution'].get(str(lvl),0)}")
    L.append("")
    L.append("CLUTCHES WON:")
    for s in r["clutches"]:
        c = s["clutch"]
        L.append(f"  R{s['round']} {s['player']} {c['starting_situation']} "
                 f"({c['kills']} clutch kills, start HP {c['hp_start']})")
    if not r["clutches"]:
        L.append("  (none)")
    L.append("")
    L.append("MULTI-KILLS (3K+):")
    for s in r["multikills"]:
        L.append(f"  R{s['round']} {s['player']} {s['kills']}K ({s['sequence_duration']}s)")
    if not r["multikills"]:
        L.append("  (none)")
    L.append("")
    L.append("=" * 60)
    L.append("DEBUG — CHRONOLOGICAL EVENT TIMELINE (why each line fired / was ignored)")
    L.append("=" * 60)
    L.extend(debug_lines)
    return "\n".join(L)


def make_source(path=None, tickrate=64):
    if path and os.path.exists(path):
        return DemoDataSource(path, tickrate=tickrate)
    return SyntheticDataSource(tickrate=tickrate)
