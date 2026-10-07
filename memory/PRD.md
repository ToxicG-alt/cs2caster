# PRD — CS2 AI Esports Caster

## Original problem statement
Build an AI esports caster for CS2 ESEA matches. Pipeline: CS2 match → game-state extraction →
intelligent highlight detection → tactical analysis → AI commentary → realistic caster voice →
audio/broadcast. First version works from a completed `.dem`. Architecture MUST allow swapping the
completed-demo input for a delayed/live GOTV source later without rewriting analysis/commentary/
TTS/broadcast. Deterministic Game-Understanding + Highlight layer MUST sit BEFORE the LLM.

## Architecture
- FastAPI backend + React (Vite) dashboard + MongoDB (match metadata/results).
- Python pipeline package `backend/cs2/`: datasource (ABC + DemoDataSource/SyntheticDataSource),
  game_state, detection (clutch/multikill/mechanical/scoring/clustering), match_memory,
  llm_client (Analyst→Caster, swappable), tts_client (ElevenLabs, swappable), pipeline orchestrator.
- Provider abstractions everywhere; scoring/timing/hype fully config-driven (`cs2/config.py`).

## User personas
- CS2 amateur/semi-pro player casting their own ESEA matches with an AI caster.

## Core requirements (static)
- Deterministic highlight detection before any LLM call (cost + anti-hallucination).
- Hype levels 0–5 with real contrast; silence is valid.
- Factual-only commentary; confidence levels on mechanical claims.
- Swappable LLM + TTS providers; data-source abstraction for future live/delayed GOTV.

## Implemented (2026-06)
- demoparser2-based DemoDataSource + built-in SyntheticDataSource (de_nuke sample).
- Game-state reconstruction, normalized GameEvent schema.
- Deterministic detectors: opening/multi-kill, clutch (last-alive logic), mechanical timing,
  configurable scoring + hype levels, situation clustering.
- Match memory (factual stats/clutch/multikill counts).
- Two-stage AI: Analyst (JSON) → Caster (natural line) via OpenAI/Emergent key; graceful fallback.
- ElevenLabs TTS (graceful no-key fallback), per-clip audio served by backend.
- Outputs: commentary.json, match_report.txt (debug + QC hype distribution), result.json.
- React dashboard: upload/sample, progress polling, scoreboard, stats, hype distribution,
  biggest highlights, commentary timeline with audio playback.

## Verified
- Full pipeline end-to-end with real LLM on sample match: clutch 1v3 (L5), ACE/quad (L5),
  triple (L4), good L1–L2 filler contrast; report + commentary.json generated.
- NOT yet verified against a real uploaded .dem (no demo file available during build) — DemoDataSource
  is defensive but should be validated with a real ESEA .dem.

## Backlog / next
- P0: validate DemoDataSource against a real ESEA .dem; add ELEVENLABS_API_KEY to enable voice.
- P1: economy analysis (full/eco/force), positional/spatial detectors from tick coords.
- P1: combined single caster_audio.wav timeline with silence gaps for broadcast.
- P2: OBS/FFmpeg sync + delayed GOTV LiveDataSource (delay_seconds), CV video layer.
