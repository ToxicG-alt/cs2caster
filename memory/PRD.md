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
- demoparser2 (pandas) DemoDataSource + SyntheticDataSource; chronological normalized GameEvent stream.
- **Event-driven CommentaryEngine (`cs2/commentary_engine.py`)**: walks events in DEMO-TIME order,
  maintains running game state, scores each event from PAST+CURRENT facts only (never future),
  detects opening kills, rapid multi-kill escalation, clutch situations (recognized BEFORE the
  first clutch kill), clutch progression (1vN→1v(N-1)), clutch wins, bomb plants, short round-end.
- Deterministic priority scoring + thresholds + cooldown + major-event interrupt (all in config).
- Credit control: simple events use FREE templates; LLM only for 1v3+ clutch WINS (configurable).
  Sample match = 1 LLM call; a lopsided match with no won clutches = 0 LLM calls.
- Debug timeline in match_report.txt (COMMENT/IGNORE with reason + METHOD per event).
- ElevenLabs TTS (preferred) with automatic OpenAI onyx fallback; per-line audio clips.
- Process-from-URL endpoint for large demos (.dem/.dem.gz/.dem.bz2).
- React dashboard: chronological commentary timeline, TEMPLATE/LLM badges, LLM-call counter,
  hype distribution, biggest highlights, audio playback.

## Verified
- Real 60MB de_mirage .dem parses end-to-end through the live app (upload + URL paths).
- Chronological ordering + no-future-events property confirmed (templates present-tense; LLM
  payload only carries alive_before/after of the current kill + strictly-past recent_kills).
- LLM clutch-win path fires correctly on the synthetic won 1v3 (1 call) with a factual live line.

## Superseded
- OLD round-summary path (detect_round_highlights + per-situation analyst/caster) REMOVED from
  pipeline; game_state.py/detection.py/match_memory.py retained only for helpers.

## Backlog / next
- P1: widen LLM routing to eco upsets / comebacks (needs economy data) — kept off for credit control.
- P1: synchronized single caster_audio.wav timeline for OBS playback at demo timestamps.
- P2: OBS/FFmpeg + delayed GOTV LiveDataSource (delay_seconds); CV video layer.
