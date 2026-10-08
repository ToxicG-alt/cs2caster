import { useEffect, useRef, useState, useCallback } from "react";
import "@/index.css";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  Radio, Upload, Play, Pause, Loader2, Trophy, Crosshair, Flame,
  Volume2, Activity, Target, Zap, ShieldAlert, FileText, ChevronRight, Download,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const HYPE = {
  0: { label: "SILENCE", color: "#4b5563", glow: "transparent" },
  1: { label: "INFO", color: "#64748b", glow: "transparent" },
  2: { label: "INTERESTING", color: "#38bdf8", glow: "#38bdf855" },
  3: { label: "EXCITED", color: "#22d3ee", glow: "#22d3ee55" },
  4: { label: "HYPE", color: "#f59e0b", glow: "#f59e0b66" },
  5: { label: "INSANE", color: "#ef4444", glow: "#ef4444aa" },
};

function HypeBadge({ level, size = "sm" }) {
  const h = HYPE[level] || HYPE[0];
  const pad = size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-[11px]";
  return (
    <span data-testid={`hype-badge-${level}`} className={`font-display font-700 tracking-wider rounded ${pad}`}
      style={{ color: "#0b0e14", background: h.color, boxShadow: `0 0 16px ${h.glow}` }}>
      L{level} · {h.label}
    </span>
  );
}

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="glass rounded-lg p-4 flex items-center gap-3" data-testid={`stat-${label}`}>
      <div className="w-10 h-10 rounded-md grid place-items-center" style={{ background: `${accent}22`, color: accent }}>
        <Icon size={20} />
      </div>
      <div>
        <div className="text-2xl font-display font-700 leading-none">{value}</div>
        <div className="text-xs text-muted-foreground uppercase tracking-wide mt-1">{label}</div>
      </div>
    </div>
  );
}

function AudioButton({ src }) {
  const ref = useRef(null);
  const [playing, setPlaying] = useState(false);
  if (!src) return (
    <span className="text-[11px] text-muted-foreground flex items-center gap-1"><Volume2 size={12} /> no audio</span>
  );
  return (
    <>
      <button data-testid="play-audio-btn" onClick={() => {
        const a = ref.current;
        if (playing) { a.pause(); } else { a.play(); }
      }}
        className="flex items-center gap-1.5 text-xs font-600 px-3 py-1.5 rounded-full transition-colors"
        style={{ background: "hsl(var(--primary))", color: "#0b0e14" }}>
        {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Playing" : "Hear caster"}
      </button>
      <audio ref={ref} src={src} onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
    </>
  );
}

function HypeDistribution({ dist }) {
  const max = Math.max(1, ...Object.values(dist || {}));
  return (
    <div className="glass rounded-lg p-5" data-testid="hype-distribution">
      <h3 className="font-display font-600 uppercase tracking-wider text-sm mb-4 flex items-center gap-2">
        <Activity size={16} className="text-primary" /> Hype Distribution
      </h3>
      <div className="space-y-2">
        {[0, 1, 2, 3, 4, 5].map((lvl) => {
          const h = HYPE[lvl];
          const v = (dist && dist[lvl]) || 0;
          return (
            <div key={lvl} className="flex items-center gap-3">
              <span className="font-mono text-xs w-5 text-muted-foreground">L{lvl}</span>
              <div className="flex-1 h-5 bg-secondary rounded overflow-hidden">
                <motion.div initial={{ width: 0 }} animate={{ width: `${(v / max) * 100}%` }}
                  transition={{ duration: 0.6, delay: lvl * 0.06 }}
                  className="h-full rounded" style={{ background: h.color }} />
              </div>
              <span className="font-mono text-xs w-6 text-right">{v}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [matches, setMatches] = useState([]);
  const [active, setActive] = useState(null);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [demoUrl, setDemoUrl] = useState("");
  const fileRef = useRef(null);

  const loadMatches = useCallback(async () => {
    try { const r = await axios.get(`${API}/cs2/matches`); setMatches(r.data); } catch (e) { /* noop */ }
  }, []);

  useEffect(() => { loadMatches(); }, [loadMatches]);

  // poll active match until done
  useEffect(() => {
    if (!active) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await axios.get(`${API}/cs2/matches/${active}`);
        setDetail(r.data);
        if (r.data.status === "processing" && !stop) setTimeout(tick, 2000);
        else loadMatches();
      } catch (e) { /* noop */ }
    };
    tick();
    return () => { stop = true; };
  }, [active, loadMatches]);

  const startSample = async () => {
    setBusy(true);
    try { const r = await axios.post(`${API}/cs2/sample`); setActive(r.data.id); setDetail(null); }
    finally { setBusy(false); }
  };
  const onUpload = async (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const r = await axios.post(`${API}/cs2/upload`, fd);
      setActive(r.data.id); setDetail(null);
    } catch (err) { alert("Upload failed: " + (err?.response?.data?.detail || err.message)); }
    finally { setBusy(false); e.target.value = ""; }
  };
  const onProcessUrl = async () => {
    const url = demoUrl.trim(); if (!url) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/cs2/process-url`, { url });
      setActive(r.data.id); setDetail(null); setDemoUrl("");
    } catch (err) { alert("Failed: " + (err?.response?.data?.detail || err.message)); }
    finally { setBusy(false); }
  };

  const res = detail?.result;
  const processing = detail && detail.status === "processing";
  const lp = detail?.live_progress;

  return (
    <div className="min-h-screen scan-line">
      <header className="border-b border-border glass sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-md grid place-items-center pulse-ring"
              style={{ background: "hsl(var(--primary))", color: "#0b0e14" }}>
              <Radio size={22} />
            </div>
            <div>
              <h1 className="font-display font-700 text-xl tracking-wide leading-none">CS2 AI CASTER</h1>
              <p className="text-[11px] text-muted-foreground uppercase tracking-[0.25em] mt-0.5">
                demo → highlights → commentary → voice
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button data-testid="upload-btn" onClick={() => fileRef.current?.click()} disabled={busy}
              className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-600 border border-border hover:bg-secondary transition-colors disabled:opacity-50">
              <Upload size={15} /> Upload .dem
            </button>
            <input ref={fileRef} type="file" accept=".dem" onChange={onUpload} className="hidden" />
            <button data-testid="sample-btn" onClick={startSample} disabled={busy}
              className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-700 transition-transform hover:scale-[1.03] disabled:opacity-50"
              style={{ background: "hsl(var(--primary))", color: "#0b0e14" }}>
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Zap size={15} />} Run Sample Match
            </button>
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-6 pb-3 flex items-center gap-2">
          <input data-testid="demo-url-input" value={demoUrl} onChange={(e) => setDemoUrl(e.target.value)}
            placeholder="Paste a direct .dem / .dem.gz / .dem.bz2 link (for large ESEA/FACEIT demos)"
            className="flex-1 bg-secondary/60 border border-border rounded-md px-3 py-2 text-sm font-mono outline-none focus:border-primary/60 transition-colors" />
          <button data-testid="process-url-btn" onClick={onProcessUrl} disabled={busy || !demoUrl.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-600 border border-border hover:bg-secondary transition-colors disabled:opacity-40 whitespace-nowrap">
            <ChevronRight size={15} /> Process from URL
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-8">
        {/* Sidebar */}
        <aside className="space-y-3">
          <h2 className="font-display uppercase text-xs tracking-[0.2em] text-muted-foreground px-1">Matches</h2>
          {matches.length === 0 && (
            <p className="text-sm text-muted-foreground px-1">No matches yet. Run the sample to see it work.</p>
          )}
          {matches.map((m) => (
            <button key={m.id} data-testid={`match-item-${m.id}`} onClick={() => { setActive(m.id); setDetail(null); }}
              className={`w-full text-left glass rounded-lg p-3 transition-all hover:border-primary/50 ${active === m.id ? "border-primary" : ""}`}>
              <div className="flex items-center justify-between">
                <span className="font-600 text-sm truncate">{m.filename}</span>
                <ChevronRight size={14} className="text-muted-foreground shrink-0" />
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-[10px] uppercase font-700 tracking-wide px-1.5 py-0.5 rounded ${
                  m.status === "done" ? "bg-emerald-500/20 text-emerald-400" :
                  m.status === "error" ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"}`}>
                  {m.status}
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">{m.source}</span>
              </div>
            </button>
          ))}
        </aside>

        {/* Main panel */}
        <section>
          {!detail && (
            <div className="glass rounded-xl p-12 text-center" data-testid="empty-state">
              <Crosshair size={48} className="mx-auto text-primary mb-4" />
              <h3 className="font-display text-2xl font-700 mb-2">Your AI esports caster awaits</h3>
              <p className="text-muted-foreground max-w-md mx-auto">
                Upload a completed CS2 <span className="font-mono text-foreground">.dem</span> file, or run the built-in
                sample match. The deterministic engine detects clutches, multi-kills and mechanical sequences, then the
                AI analyst + caster generate commentary.
              </p>
            </div>
          )}

          {processing && (
            <div className="glass rounded-xl p-10 text-center" data-testid="processing-state">
              <Loader2 size={40} className="mx-auto animate-spin text-primary mb-4" />
              <h3 className="font-display text-xl font-700 uppercase tracking-wide">Processing match…</h3>
              <p className="text-sm text-muted-foreground mt-1 font-mono">{lp?.stage || "starting"}</p>
              <div className="max-w-sm mx-auto h-2 bg-secondary rounded-full overflow-hidden mt-5">
                <motion.div className="h-full" style={{ background: "hsl(var(--primary))" }}
                  animate={{ width: `${lp?.progress || 5}%` }} transition={{ duration: 0.5 }} />
              </div>
              <p className="text-xs text-muted-foreground mt-2">{lp?.progress || 5}%</p>
            </div>
          )}

          {detail?.status === "error" && (
            <div className="glass rounded-xl p-8 border-destructive" data-testid="error-state">
              <ShieldAlert className="text-destructive mb-2" />
              <h3 className="font-display font-700 text-lg">Processing failed</h3>
              <p className="text-sm text-muted-foreground font-mono mt-2">{detail.error}</p>
            </div>
          )}

          {res && (
            <div className="space-y-8">
              {/* Scoreboard */}
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                className="glass rounded-xl p-6" data-testid="scoreboard">
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-muted-foreground">Map</p>
                    <h2 className="font-display text-3xl font-700">{res.map}</h2>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <p className="text-xs text-accent uppercase font-600">{res.team_ct}</p>
                      <p className="font-display text-5xl font-700 text-accent">{res.score.ct}</p>
                    </div>
                    <span className="font-display text-2xl text-muted-foreground">:</span>
                    <div className="text-center">
                      <p className="text-xs text-primary uppercase font-600">{res.team_t}</p>
                      <p className="font-display text-5xl font-700 text-primary">{res.score.t}</p>
                    </div>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    <p>Caster: <span className="text-foreground font-600">{res.caster}</span></p>
                    <p className="mt-1">LLM calls: <span className="text-foreground font-mono font-600" data-testid="llm-calls">{res.llm_calls ?? 0}</span> <span className="text-muted-foreground">(rest free templates)</span></p>
                    <p className="mt-1">{res.tts_available
                      ? <span className="text-emerald-400">● voice on</span>
                      : <span className="text-amber-400">● voice off (add ElevenLabs key)</span>}</p>
                    {res.full_audio && (
                      <a data-testid="download-audio" href={`${API}/cs2/matches/${detail.id}/full-audio`}
                        className="inline-flex items-center gap-1.5 mt-2 px-3 py-1.5 rounded-md text-xs font-700 transition-transform hover:scale-[1.03]"
                        style={{ background: "hsl(var(--primary))", color: "#0b0e14" }}>
                        <Download size={13} /> Download synced caster audio
                      </a>
                    )}
                  </div>
                </div>
              </motion.div>

              {/* Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat icon={Target} label="Rounds" value={res.total_rounds} accent="#38bdf8" />
                <Stat icon={Crosshair} label="Kills" value={res.total_kills} accent="#f59e0b" />
                <Stat icon={Flame} label="Highlights" value={res.total_candidate_highlights} accent="#ef4444" />
                <Stat icon={Volume2} label="Commentary" value={res.total_commentary_events} accent="#22d3ee" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <HypeDistribution dist={res.hype_distribution} />
                {/* Top highlights */}
                <div className="glass rounded-lg p-5" data-testid="top-highlights">
                  <h3 className="font-display font-600 uppercase tracking-wider text-sm mb-4 flex items-center gap-2">
                    <Trophy size={16} className="text-primary" /> Biggest Highlights
                  </h3>
                  <div className="space-y-2">
                    {res.top_highlights.slice(0, 6).map((s, i) => (
                      <div key={i} className="flex items-center justify-between gap-2 py-1.5 border-b border-border/40 last:border-0">
                        <div className="min-w-0">
                          <span className="font-600 text-sm">{s.player}</span>
                          <span className="text-xs text-muted-foreground ml-2 font-mono">
                            R{s.round} · {s.situation_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="font-mono text-xs text-muted-foreground">{s.hype_score}pts</span>
                          <HypeBadge level={s.hype_level} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Commentary timeline */}
              <div data-testid="commentary-timeline">
                <h3 className="font-display font-700 uppercase tracking-wider text-lg mb-4 flex items-center gap-2">
                  <Radio size={18} className="text-primary" /> Caster Commentary
                </h3>
                <div className="space-y-3">
                  <AnimatePresence>
                    {res.commentary.map((c, i) => {
                      const h = HYPE[c.hype_level] || HYPE[0];
                      const audioSrc = c.audio
                        ? `${API}/cs2/matches/${detail.id}/audio/${c.audio.split("/").pop()}` : null;
                      return (
                        <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: Math.min(i * 0.03, 0.5) }}
                          className="glass rounded-lg p-4 border-l-2" data-testid={`commentary-${i}`}
                          style={{ borderLeftColor: h.color }}>
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                                <HypeBadge level={c.hype_level} />
                                <span className="font-mono text-[11px] text-muted-foreground">
                                  R{c.round} · {c.timestamp}s · imp {c.importance}
                                </span>
                                <span className="text-[11px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground font-mono">
                                  {c.confidence}
                                </span>
                                {c.mode && c.mode !== "play" && (
                                  <span className={`text-[11px] px-1.5 py-0.5 rounded font-mono font-600 ${c.mode === "analysis" ? "bg-accent/25 text-accent" : "bg-secondary text-muted-foreground"}`}>
                                    {c.mode}
                                  </span>
                                )}
                                {c.method && (
                                  <span className={`text-[11px] px-1.5 py-0.5 rounded font-mono font-600 ${c.method === "LLM" ? "bg-primary/25 text-primary" : "bg-secondary text-muted-foreground"}`}>
                                    {c.method}
                                  </span>
                                )}
                              </div>
                              <p className="font-display text-lg leading-snug"
                                style={{ color: c.hype_level >= 4 ? h.color : undefined }}>
                                "{c.text}"
                              </p>
                              {c.facts_used?.length > 0 && (
                                <p className="text-[11px] text-muted-foreground mt-1.5 font-mono">
                                  facts: {c.facts_used.slice(0, 4).join(" · ")}
                                </p>
                              )}
                            </div>
                            <div className="shrink-0"><AudioButton src={audioSrc} /></div>
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              </div>

              {/* Report hint */}
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <FileText size={12} /> Full debug report, commentary.json and audio clips are saved server-side per match.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
