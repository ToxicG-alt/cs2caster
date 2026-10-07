# CS2 AI Esports Caster — MVP

`.dem → parser → game events → highlight detection → AI analysis → commentary → TTS → audio`

This is the **completed-demo MVP**. The architecture is deliberately built so the demo input
can later be swapped for a delayed/live GOTV feed **without rewriting** analysis, commentary,
TTS or broadcast code — only the data-source layer changes.

---

## 1. Technology research & decisions

### Demo parser — **demoparser2** (selected)
- `demoparser2` (Rust-backed, `pip install demoparser2`) is the fastest, most actively maintained
  CS2 demo parser. Awpy v2 wraps this same engine; using it directly keeps us lean.
- **Reliable from a .dem:** map, rounds (`round_start`/`round_end` with winner & reason), kills
  (`player_death`: attacker, victim, weapon, headshot, assister), bomb plant/defuse/explode,
  damage (`player_hurt`), shots (`weapon_fire`), ticks for health/armor/team/position/velocity
  via `parse_ticks(...)`.
- **Harder / needs care:** exact per-player economy & buy intent, "tactical intent" (lurks,
  fakes), and anything the engine doesn't record. Team *clan names* vary by demo; we fall back to
  CT/T sides. Tactical intent and crosshair/visual flicks are NOT provable from demo data.

### LLM — **OpenAI GPT (via Emergent universal key)**, provider-swappable
- Strong structured-JSON reliability for the two-stage Analyst → Caster design. Swap to
  Gemini/Claude by changing `config.llm.provider/model` only.

### TTS — **ElevenLabs**, provider-swappable
- Most believable, expressive caster voice. Needs your own `ELEVENLABS_API_KEY` (the Emergent key
  does **not** cover ElevenLabs). Without a key the pipeline still produces commentary + report;
  it just skips audio (graceful).

### Broadcast — deferred (by design)
- OBS/FFmpeg integration is intentionally **not** in the MVP. Every commentary line already carries
  a `timestamp` so audio can later be synced to video.

---

## 2. Architecture (deterministic engine BEFORE the LLM)

```
CS2 .dem
  └─ parser/datasource (demoparser2)        -> normalized GameEvent stream
      └─ game/game_state                    -> match / round / player reconstruction
          └─ detection (deterministic)      -> clutch, multi-kill, mechanical, scoring, hype levels
              └─ detection.cluster          -> merge bursts into single situations
                  └─ analysis/match_memory  -> factual narrative memory
                      └─ analysis/llm Stage A (Analyst, JSON)
                          └─ commentary Stage B (Caster, natural line)
                              └─ tts (ElevenLabs)      -> audio clips
                                  └─ commentary.json + match_report.txt + result.json
```

The LLM **never** sees raw events — only pre-scored, pre-clustered situations. This controls cost
(≈tens of calls per match, not thousands) and kills hallucination (facts come from Python).

### Key abstractions
- `cs2/datasource.py` — `GameDataSource` ABC. `DemoDataSource` (real .dem) + `SyntheticDataSource`
  (built-in sample so the whole pipeline is testable with no file). A future `LiveGOTVDataSource`
  slots in here with zero downstream changes.
- `cs2/llm_client.py` — `LLMProvider` ABC, swappable providers, graceful deterministic fallback.
- `cs2/tts_client.py` — `TTSProvider` ABC (`ElevenLabsProvider`), graceful no-key fallback.
- `cs2/config.py` — **all scoring/timing/hype thresholds are configurable**, nothing hardcoded.

---

## 3. Running it

Web dashboard: click **Run Sample Match** (no file needed) or **Upload .dem**. The backend
processes in the background and the dashboard polls progress, then shows the scoreboard, hype
distribution, biggest highlights and the caster commentary timeline.

Outputs are written server-side per match under `backend/output/<match_id>/`:
`commentary.json`, `match_report.txt` (incl. debug blocks + QC hype distribution), `result.json`,
and `audio/clip_*.mp3`.

### Enable the caster voice
Add your key to `backend/.env`:
```
ELEVENLABS_API_KEY=your_key_here
```
then `sudo supervisorctl restart backend`. New matches will include audio.

---

## 4. Hype levels (contrast is the point)
`0 silence · 1 info · 2 interesting · 3 excited · 4 hype · 5 INSANE`
Most of a match is L1–L2; clutches/aces are rare L5. The QC hype distribution in the report lets
you check the caster isn't too quiet or too excited.

## 5. Confidence / anti-hallucination
Mechanical claims carry `CERTAIN / STRONGLY_INFERRED / UNCERTAIN`. The caster prompt forbids
inventing kills, HP, weapons, timings, positions, score or history. It interprets facts only.

---

## Limitations (what a demo can & can't prove)
- **Provable:** who killed whom, weapon, headshot, timing between kills, HP at kill tick, bomb
  state, round winner/reason, positions/velocity (via ticks).
- **Not provable from demo alone:** visual flicks / 180° no-scopes, "through-smoke" intent, fakes
  vs. real executes, opponent economy with certainty. We deliberately say *"an incredibly fast AWP
  double"* (timing-provable) rather than *"a 180 flick through smoke"* (not provable).
- **Where computer vision would help later:** exact crosshair movement, no-scopes, smoke/flash
  visual context, spectacular movement — documented as a future layer, not in the MVP.

## Future: live / delayed GOTV (designed, not built)
Add a `LiveGOTVDataSource(GameDataSource)` feeding a rolling game-state buffer with a configurable
`delay_seconds` (e.g. 600). The analysis system does not need to know the delay is 0, 60 or 600s.
