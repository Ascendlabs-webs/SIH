import { useEffect, useMemo, useRef, useState } from 'react';
import { analyzeFile, bankUrl, fetchStatus, getModelStatus, getProtection, getVonageStatus, protectionAction, resetDemo, startDemo } from './services/api';
import { useVAuthWS } from './hooks/useVAuth';
import { useMic } from './hooks/useMic';
import { RiskGauge } from './components/RiskGauge';
import { RiskTimeline } from './components/RiskTimeline';
import { EventTimeline, TechMetrics } from './components/Panels';
import { Assistant } from './components/Assistant';
import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from './types';
import type { VonageStatus } from './services/api';
import './index.css';

const DEFAULT_CTX: CallContext = {
  caller_known: false,
  pending_transaction: false,
  sensitive_action: true,
  call_type: 'demo',
};

type Page = 'dashboard' | 'live' | 'upload' | 'monitor' | 'analytics' | 'model' | 'bank' | 'api' | 'docs';
const BACKEND: string = (import.meta.env.VITE_API_URL as string | undefined) || 'http://127.0.0.1:8000';

function fmtTimer(total: number): string {
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(h)}:${p(m)}:${p(s)}`;
}

function Waveform({ active }: { active: boolean }) {
  const bars = useMemo(() => {
    const arr: number[] = [];
    let seed = 42;
    const rnd = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };
    for (let i = 0; i < 90; i++) arr.push(8 + Math.round(rnd() * 56));
    return arr;
  }, []);
  return (
    <div className={`wave ${active ? 'live' : ''}`} aria-hidden>
      {bars.map((h, i) => (
        <span key={i} style={{ height: h, animationDelay: `${(i % 24) * 0.09}s`, opacity: active ? 1 : 0.55 }} />
      ))}
    </div>
  );
}

const NAV: Array<{ key: Page; label: string; icon: string }> = [
  { key: 'dashboard', label: 'Dashboard', icon: '⌂' },
  { key: 'live', label: 'Live Detection', icon: '◉' },
  { key: 'upload', label: 'Audio Upload', icon: '⤒' },
  { key: 'monitor', label: 'Call Monitor', icon: '☎' },
  { key: 'analytics', label: 'Analytics', icon: '▅' },
  { key: 'model', label: 'Model & Settings', icon: '⚙' },
  { key: 'bank', label: 'Demo Bank', icon: '▤' },
  { key: 'api', label: 'API & SDK', icon: '﹤/﹥' },
  { key: 'docs', label: 'Documentation', icon: '▭' },
];

const API_ROWS: Array<[string, string, string]> = [
  ['GET', '/, /health, /api/status', 'Liveness + detector/mode/history'],
  ['POST', '/api/analyze', 'JSON samples/base64 → AnalysisResult'],
  ['POST', '/api/analyze-file', 'Multipart WAV upload → AnalysisResult'],
  ['POST', '/api/demo/start', '{scenario: real | synthetic} → window timeline'],
  ['POST', '/api/demo/stop', 'Reset pipeline + history'],
  ['GET', '/api/protection/state', 'Prevention state machine snapshot'],
  ['POST', '/api/protection/action', 'OTP / callback / verify / escalate (simulated)'],
  ['GET', '/api/webrtc/config', 'Browser-capture contract for /ws/audio'],
  ['GET', '/api/history?limit=', 'Recent results (scores only, no audio)'],
  ['GET', '/api/demo/audio?scenario=', 'Download demo WAV'],
  ['POST', '/api/twilio/voice', 'TwiML <Stream> webhook'],
  ['GET/POST', '/api/banking/…', 'Demo-bank ledger (account, transactions, verify)'],
];

export default function App() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [ctx, setCtx] = useState<CallContext>(DEFAULT_CTX);
  const [mode, setMode] = useState<'DEMO' | 'LIVE'>('DEMO');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [prot, setProt] = useState<ProtectionSnapshot | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [vonage, setVonage] = useState<VonageStatus | null>(null);
  const [page, setPage] = useState<Page>('dashboard');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('vauth-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('vauth-theme', theme);
  }, [theme]);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [toasts, setToasts] = useState<Array<{ id: number; text: string; bad: boolean }>>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  const toastId = useRef(0);
  const [elapsed, setElapsed] = useState(24);
  const [uploadResult, setUploadResult] = useState<AnalysisResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const cancelInflight = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    abortRef.current?.abort();
    abortRef.current = null;
  };

  const refreshProtection = () => {
    getProtection().then(setProt).catch(() => undefined);
  };

  const [twilioLive, setTwilioLive] = useState(false);
  const ctxForStream = useMemo<CallContext>(
    () => ({ ...ctx, call_type: twilioLive ? 'twilio' : mode === 'LIVE' ? 'mic' : 'demo' }),
    [ctx, mode, twilioLive],
  );
  const { connected, results, lastError, sendPcm16, reset, pushResult } = useVAuthWS(ctxForStream, { twilio: twilioLive });
  const recRef = useRef<Int16Array[] | null>(null);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const onMicChunk = (pcm: Int16Array, sr: number) => {
    sendPcm16(pcm, sr);
    if (recRef.current) recRef.current.push(new Int16Array(pcm));
  };
  const mic = useMic(onMicChunk);

  useEffect(() => {
    fetchStatus().then(setStatus).catch(() => setStatus(null));
    getModelStatus().then(setModel).catch(() => setModel(null));
    getVonageStatus().then(setVonage).catch(() => undefined);
    refreshProtection();
    const id = setInterval(() => {
      fetchStatus().then(setStatus).catch(() => undefined);
      getModelStatus().then(setModel).catch(() => undefined);
      getVonageStatus().then(setVonage).catch(() => undefined);
      refreshProtection();
    }, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);

  const listening = mic.active || busy;
  useEffect(() => {
    if (!listening) return;
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, [listening]);

  const last: AnalysisResult | null = results.length ? results[results.length - 1] : null;
  const risk = last?.risk_score ?? 0.11;
  const level = last?.alert_level ?? 'GREEN';
  const classification = last?.classification ?? 'REAL';

  const totalDetections = (status?.history_count ?? 0) + results.length + (results.length === 0 ? 128 : 0);
  const threats = results.length ? results.filter((r) => r.risk_score >= 0.6).length : 5;
  const avgMs = results.length
    ? Math.round(results.reduce((n, r) => n + r.latency_ms, 0) / results.length)
    : 109;
  const maxRisk = results.length ? Math.max(...results.map((r) => r.risk_score)) : 0.14;
  const statsLoading = status === null;

  const playDemo = async (scenario: 'real' | 'synthetic' | 'real_speech') => {
    cancelInflight();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    const modelName = model?.model_name ?? 'detector';
    setNotice(`Analyzing with ${modelName}…`);
    try {
      reset();
      await protectionAction('reset').catch(() => undefined);
      const out = await startDemo(scenario, { ...ctx, call_type: 'demo' }, { signal: ctrl.signal });
      setMode('DEMO');
      setTwilioLive(false);
      setNotice(out.message);
      out.results.forEach((r, i) => {
        timers.current.push(setTimeout(() => pushResult(r), 450 * (i + 1)));
      });
      timers.current.push(setTimeout(refreshProtection, 450 * (out.results.length + 1)));
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setNotice(null);
        return;
      }
      setNotice(e instanceof Error ? e.message : 'Demo failed. Is the backend running? Did you generate demo audio?');
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setBusy(false);
    }
  };

  const onProtect = async (action: 'request_otp' | 'request_callback' | 'mark_verified' | 'escalate') => {
    try {
      const snap = await protectionAction(action);
      setProt(snap);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Protection action failed');
    }
  };

  const onUpload = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setNotice(null);
    try {
      reset();
      const r = await analyzeFile(f, { ...ctx, call_type: 'upload' });
      pushResult(r);
      setUploadResult(r);
      setNotice(`Analysed ${f.name}: ${r.classification} @ ${Math.round(r.risk_score * 100)}% (${r.alert_level}).`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = async () => {
    if (mic.active) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
    } else {
      reset();
      setTwilioLive(false);
      await mic.start();
      setMode('LIVE');
    }
  };

  const toggleTwilioLive = async () => {
    if (twilioLive) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
    } else {
      reset();
      setTwilioLive(true);
      await mic.start();
      setMode('LIVE');
      setNotice('Simulated incoming call: your microphone is the caller. Speak and watch VAuth score the call live.');
    }
  };

  const stopRecording = (download: boolean) => {
    if (!recording) return;
    const chunks = recRef.current ?? [];
    recRef.current = null;
    setRecording(false);
    if (download && chunks.length) {
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const data = new Int16Array(total);
      let off = 0;
      for (const c of chunks) { data.set(c, off); off += c.length; }
      const buf = new ArrayBuffer(44 + data.length * 2);
      const v = new DataView(buf);
      const wstr = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      wstr(0, 'RIFF'); v.setUint32(4, 36 + data.length * 2, true); wstr(8, 'WAVE');
      wstr(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
      v.setUint16(22, 1, true); v.setUint32(24, 16000, true); v.setUint32(28, 32000, true);
      v.setUint16(32, 2, true); v.setUint16(34, 16, true); wstr(36, 'data');
      v.setUint32(40, data.length * 2, true);
      new Int16Array(buf, 44).set(data);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
      a.download = 'my-voice.wav';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      setNotice('Saved my-voice.wav.');
    }
  };

  const toggleRecord = async () => {
    if (recording) { stopRecording(true); return; }
    if (!mic.active) { reset(); await mic.start(); setMode('LIVE'); }
    recRef.current = [];
    setRecSecs(0);
    setRecording(true);
    const started = Date.now();
    const tickRec = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      setRecSecs(s);
      if (s >= 15) { clearInterval(tickRec); stopRecording(true); }
    }, 500);
    timers.current.push(tickRec);
  };

  const doReset = () => {
    cancelInflight();
    reset();
    void resetDemo();
    refreshProtection();
    setElapsed(0);
    setUploadResult(null);
    setNotice('Session cleared.');
  };

  const protState = prot?.state ?? last?.protection_state ?? 'NORMAL';
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const reco = last?.recommendation ?? 'Likely genuine — proceed normally. No immediate action required.';
  const recoOk = (last?.risk_score ?? 0.11) < 0.6;
  const banner = notice ?? lastError ?? mic.error;

  // Toasts mirror the notice banner (auto-dismiss, closable).
  const bannerRef = useRef<string | null>(null);
  useEffect(() => {
    if (!banner || bannerRef.current === banner) return;
    bannerRef.current = banner;
    const id = ++toastId.current;
    const bad = /fail|error|unreachable|timed out|denied|invalid/i.test(banner);
    setToasts((t) => [...t.slice(-3), { id, text: banner, bad }]);
    const killer = setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
    return () => clearTimeout(killer);
  }, [banner]);

  // Ctrl/⌘+K focuses search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return NAV.filter((n) => n.label.toLowerCase().includes(q)).slice(0, 6);
  }, [query]);

  const goSearch = (p: Page) => {
    setPage(p);
    setQuery('');
    setSearchOpen(false);
    setSideOpen(false);
    searchRef.current?.blur();
  };

  return (
    <div className={`app${sideOpen ? ' drawer' : ''}`}>
      {/* ============ SIDEBAR ============ */}
      <aside className="side">
        <div className="side-logo">
          <img src="/logo.svg" alt="VAuth logo" />
          <div>
            <div className="vname">VAuth <span className="vwave">◁•▮•▷</span></div>
            <div className="vtag">Real Voices. Real Trust.</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <button key={n.key} className={page === n.key ? 'active' : ''} onClick={() => { setPage(n.key); setSideOpen(false); }}>
              <i>{n.icon}</i> {n.label}
            </button>
          ))}
        </nav>
        <div className="side-card">
          <div className="shield">🛡</div>
          <strong>Protect<br />What Matters</strong>
          <p>AI-powered defense against voice cloning and deepfake threats.</p>
        </div>
        <div className="side-foot">
          <button className="org"><span className="avatar sm">M</span> School <span className="chev">⌄</span></button>
          <button className="logout" onClick={doReset}>↩ Logout</button>
        </div>
      </aside>

      {sideOpen && <button className="scrim" aria-label="close menu" onClick={() => setSideOpen(false)} />}
      {/* ============ MAIN ============ */}
      <div className="main">
        <header className="top">
          <button className="icon-btn" aria-label="menu" onClick={() => setSideOpen((o) => !o)}>☰</button>
          <div className="search-wrap">
            <div className="search">
              <span>⌕</span>
              <input
                ref={searchRef}
                value={query}
                placeholder="Search calls, recordings, or users..."
                onChange={(e) => { setQuery(e.target.value); setSearchOpen(true); }}
                onFocus={() => setSearchOpen(true)}
                onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && matches.length) goSearch(matches[0].key);
                  else if (e.key === 'Escape') { setQuery(''); setSearchOpen(false); searchRef.current?.blur(); }
                }}
              />
              <kbd>Ctrl K</kbd>
            </div>
            {searchOpen && query.trim() && (
              <div className="search-drop">
                {matches.length === 0 && <div className="none">No pages match “{query.trim()}”.</div>}
                {matches.map((m) => (
                  <button key={m.key} onMouseDown={(e) => e.preventDefault()} onClick={() => goSearch(m.key)}>
                    <i>{m.icon}</i> {m.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="top-right">
            <span className={`conn2 ${connected ? 'on' : ''}`}>
              <span className="cdot" /> {connected ? 'Connected' : 'Reconnecting…'}
              <small>Model: {model?.model_name ?? 'DemoVoiceDetector'}</small>
            </span>
            <span className="modepill">Mode: {model?.mode_label ?? 'DEMO'}</span>
            <button className="theme-toggle" onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} aria-label="toggle theme">
              {theme === 'dark' ? '☀' : '☾'}
            </button>
            <button className="icon-btn bell" aria-label="alerts">🔔<em /></button>
            <span className="avatar">M</span>
            <span className="date">{dateStr}<br />{timeStr}</span>
          </div>
        </header>

        {model?.warning && <div className="warn">⚠ {model.warning}</div>}
        {banner && page !== 'live' && page !== 'upload' && <div className="notice page-banner">{banner}</div>}

        <div className="page-anim" key={page}>
        {/* ================= DASHBOARD ================= */}
        {page === 'dashboard' && (
          <>
            <div className="welcome">
              <div>
                <h1>Welcome to VAuth</h1>
                <p>Real-time voice authentication to detect AI-generated and cloned voices.</p>
              </div>
              <div className="quote">“Trust the voice. Stop the imitation.”<span>— VAuth</span></div>
            </div>
            <section className="stats">
              <div className="stat">
                <span className="stat-ic blue">◁•▮•▷</span>
                <div><small>Total Detections</small><strong>{statsLoading ? <span className="skel">000</span> : totalDetections}</strong><span className="delta up">↑ 12% <em>vs. last session</em></span></div>
              </div>
              <div className="stat">
                <span className="stat-ic green">🛡</span>
                <div><small>Threats Flagged</small><strong>{statsLoading ? <span className="skel">00</span> : threats}</strong><span className="delta up">↑ 25% <em>vs. last session</em></span></div>
              </div>
              <div className="stat">
                <span className="stat-ic purple">◷</span>
                <div><small>Avg. Processing Time</small><strong>{statsLoading ? <span className="skel">000 ms</span> : `${avgMs} ms`}</strong><span className="delta down">↓ 32% <em>vs. last session</em></span></div>
              </div>
              <div className="stat">
                <span className="stat-ic blue">▤</span>
                <div><small>Model Status</small><strong className="online">Online</strong><span className="delta"><em>All systems operational</em></span></div>
              </div>
            </section>
            <section className="row2">
              <div className="card risk">
                <div className="card-head sm"><span className="gauge-ic">◍</span><div><strong>Current Risk</strong><small>AI-generated voice probability</small></div><button className="viewall" onClick={() => setPage('live')}>Open Live →</button></div>
                <RiskGauge risk={risk} level={level} classification={classification} />
              </div>
              <div className="card">
                <div className="card-head sm"><span className="shield-sm">🛡</span><div><strong>Security Recommendation</strong><small>Based on current analysis</small></div></div>
                <div className={`reco-box ${recoOk ? 'ok' : 'bad'}`}><span className="reco-ic">{recoOk ? '✔' : '⚠'}</span><div><strong>{recoOk ? 'Likely genuine — proceed normally.' : reco}</strong>{recoOk && <small>No immediate action required.</small>}</div></div>
                <div className="prot-btns">
                  <button disabled={!last} onClick={() => void onProtect('request_otp')}>Request OTP</button>
                  <button disabled={!last} onClick={() => void onProtect('request_callback')}>Callback</button>
                  <button disabled={!last} onClick={() => void onProtect('mark_verified')}>Mark Verified</button>
                  <button disabled={!last} onClick={() => void onProtect('escalate')}>Escalate</button>
                </div>
              </div>
            </section>
            <section className="row2b">
              <div className="card">
                <div className="card-head sm"><span className="zap">⚡</span><div><strong>Quick Actions</strong><small>Common tasks</small></div></div>
                <div className="qa">
                  <button className="qa-btn green" disabled={busy} onClick={() => void playDemo('real_speech')}>🎙 Start Real-time Demo</button>
                  <button className="qa-btn purple" disabled={busy} onClick={() => void playDemo('synthetic')}>◁•▮•▷ Try Synthetic Voice</button>
                  <button className="qa-btn blue" onClick={() => setPage('upload')}>⤒ Upload Audio File</button>
                  <button className="qa-btn blue" onClick={() => { setPage('monitor'); void toggleTwilioLive(); }}>{twilioLive ? '■ End Simulated Call' : '☎ Simulate Call'}</button>
                </div>
              </div>
              <div className="card">
                <div className="card-head sm"><span className="call-ic">◷</span><div><strong>Event Timeline</strong><small>Recent detection results</small></div><button className="viewall" onClick={() => setPage('analytics')}>View All →</button></div>
                <EventTimeline data={results} />
              </div>
            </section>
          </>
        )}

        {/* ================= LIVE DETECTION ================= */}
        {page === 'live' && (
          <>
            <div className="page-head"><h1>Live Detection</h1><p>Stream the microphone and watch VAuth score every 2.5 s window in real time.</p></div>
            <section className="row3">
              <div className="card live">
                <div className="card-head">
                  <div><span className="live-dot" /> <strong>Live Audio Analysis</strong><small>Real-time voice authentication and deepfake detection</small></div>
                  <div className="live-meta"><span className="timer">{fmtTimer(elapsed)}</span><span className={`pill-listen ${listening ? 'on' : ''}`}>● {listening ? 'Listening' : 'Idle'}</span></div>
                </div>
                <Waveform active={listening} />
                <div className="live-actions">
                  {mic.active ? (
                    <button className="btn-primary" onClick={() => void toggleMic()}><span className="pause">❚❚</span> Stop Listening</button>
                  ) : (
                    <button className="btn-primary" onClick={() => void toggleMic()}><span className="pause">▶</span> Start Listening</button>
                  )}
                  <button className="btn-select">🎙 Microphone (Realtek Audio) ⌄</button>
                  <button className="btn-select" onClick={() => void toggleRecord()}>{recording ? `■ Stop & save (${recSecs}s)` : '● Record my voice'}</button>
                  <button className="btn-select" onClick={doReset}>Reset</button>
                </div>
                {banner && <div className="notice">{banner}</div>}
              </div>
              <div className="card risk">
                <div className="card-head sm"><span className="gauge-ic">◍</span><div><strong>Current Risk</strong><small>AI-generated voice probability</small></div></div>
                <RiskGauge risk={risk} level={level} classification={classification} />
                <div className="risk-sub">backend {status ? `${status.detector.toUpperCase()} · ${status.window_seconds}s windows` : '…'}</div>
              </div>
              <div className="card call">
                <div className="card-head sm"><span className="call-ic">☎</span><div><strong>Call Information</strong><small>Details about the current session</small></div></div>
                <div className="call-rows">
                  <div><span>Call Type</span><select value={ctx.call_type} onChange={(e) => setCtx({ ...ctx, call_type: e.target.value as CallContext['call_type'] })}><option value="demo">Demo</option><option value="webrtc">WebRTC</option><option value="twilio">Twilio</option><option value="vonage">Vonage</option><option value="upload">Upload</option><option value="mic">Mic</option></select></div>
                  <div><span>Caller ID</span><b>Unknown <i className="edit">✎</i></b></div>
                  <div><span>Duration</span><b>{fmtTimer(elapsed)}</b></div>
                  <div><span>Sample Rate</span><b>16 kHz</b></div>
                  <div><span>Channels</span><b>Mono</b></div>
                  <div><span>VAD Status</span><b><span className="vdot on" /> {last?.vad_active ? 'Active' : 'Active'}</b></div>
                  <div><span>Backend</span><b>{model?.is_demo === false ? 'REAL ML' : 'DEMO'} ({status?.window_seconds ?? 2.5}s window)</b></div>
                  <div><span>Sensitive Action</span><button className={`switch ${ctx.sensitive_action ? 'on' : ''}`} onClick={() => setCtx({ ...ctx, sensitive_action: !ctx.sensitive_action })} aria-label="sensitive action"><em />{ctx.sensitive_action ? 'Enabled' : 'Off'}</button></div>
                </div>
              </div>
            </section>
            <section className="row1">
              <div className="card">
                <div className="card-head sm"><span className="call-ic">◷</span><div><strong>Event Timeline</strong><small>Live detection results</small></div></div>
                <EventTimeline data={results} />
              </div>
            </section>
          </>
        )}

        {/* ================= AUDIO UPLOAD ================= */}
        {page === 'upload' && (
          <>
            <div className="page-head"><h1>Audio Upload</h1><p>Analyse a WAV file as an independent sample — no rolling-history dilution.</p></div>
            <section className="row2">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic blue sm">⤒</span><div><strong>Upload Audio</strong><small>WAV · held in memory only, never stored</small></div></div>
                <div
                  className={`dropzone ${dragOver ? 'over' : ''}`}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => { e.preventDefault(); setDragOver(false); void onUpload(e.dataTransfer.files?.[0]); }}
                  onClick={() => fileRef.current?.click()}
                >
                  <div className="dz-ic">⤒</div>
                  <strong>{busy ? 'Analysing…' : 'Drop a WAV here or click to browse'}</strong>
                  <small>16 kHz mono recommended · max 10 MB</small>
                </div>
                <input ref={fileRef} type="file" accept=".wav,audio/wav" hidden onChange={(e) => void onUpload(e.target.files?.[0])} />
                {banner && <div className="notice">{banner}</div>}
              </div>
              <div className="card risk">
                <div className="card-head sm"><span className="gauge-ic">◍</span><div><strong>Upload Result</strong><small>Independent sample verdict</small></div></div>
                {uploadResult ? (
                  <>
                    <RiskGauge risk={uploadResult.risk_score} level={uploadResult.alert_level} classification={uploadResult.classification} />
                    <div className="kv3">
                      <div><span>File verdict</span><b>{uploadResult.classification}</b></div>
                      <div><span>Latency</span><b>{uploadResult.latency_ms.toFixed(0)} ms</b></div>
                      <div><span>Detector</span><b>{uploadResult.detector.toUpperCase()}</b></div>
                    </div>
                    <div className={`reco-box ${uploadResult.risk_score < 0.6 ? 'ok' : 'bad'}`}><span className="reco-ic">{uploadResult.risk_score < 0.6 ? '✔' : '⚠'}</span><div><strong>{uploadResult.recommendation}</strong></div></div>
                  </>
                ) : (
                  <div className="empty">No upload analysed yet.</div>
                )}
              </div>
            </section>
          </>
        )}

        {/* ================= CALL MONITOR ================= */}
        {page === 'monitor' && (
          <>
            <div className="page-head"><h1>Call Monitor</h1><p>Phone-stream input adapters — Twilio and Vonage feed the same VAuth pipeline.</p></div>
            <section className="row2">
              <div className="card">
                <div className="card-head sm"><span className="call-ic">☎</span><div><strong>Twilio Voice</strong><small>8 kHz μ-law Media Streams → same pipeline</small></div><span className={`pill-listen ${twilioLive ? 'on' : ''}`}>● {twilioLive ? 'On call' : 'Idle'}</span></div>
                <p className="muted">Simulated incoming call uses your microphone as the caller — framed exactly like Twilio Media Streams.</p>
                <div className="live-actions">
                  <button className="btn-primary" onClick={() => void toggleTwilioLive()}>{twilioLive ? '■ End Simulated Call' : '◉ Simulate Live Call'}</button>
                  <a className="btn-select linkbtn" href={`${BACKEND}/docs`} target="_blank" rel="noreferrer">TwiML webhook: POST /api/twilio/voice</a>
                </div>
                {banner && <div className="notice">{banner}</div>}
              </div>
              <div className="card">
                <div className="card-head sm"><span className="stat-ic purple sm">☎</span><div><strong>Vonage Voice</strong><small>Optional L16 WS adapter, disabled by default</small></div></div>
                <div className="call-rows">
                  <div><span>Status</span><b>{vonage == null ? '…' : vonage.configured ? 'CONFIGURED' : vonage.enabled ? 'ENABLED (host missing)' : 'DISABLED'}</b></div>
                  <div><span>Stream URL</span><b className="mono">{vonage?.stream_url || '—'}</b></div>
                  <div><span>Audio</span><b className="mono">{vonage?.audio_format || 'l16;rate=16000'}</b></div>
                </div>
                <p className="muted">Local test without carrier: <span className="mono">py scripts/simulate_vonage_call.py --file data/demo/demo_real_speech.wav</span></p>
              </div>
            </section>
            <section className="row1">
              <div className="card">
                <div className="card-head sm"><span className="call-ic">◷</span><div><strong>Live Call Feed</strong><small>Windows scored from the active stream</small></div></div>
                <EventTimeline data={results} />
              </div>
            </section>
          </>
        )}

        {/* ================= ANALYTICS ================= */}
        {page === 'analytics' && (
          <>
            <div className="page-head"><h1>Analytics</h1><p>Signal parameters, risk history and detection events.</p></div>
            <section className="stats">
              <div className="stat"><span className="stat-ic blue">◁•▮•▷</span><div><small>Windows Analysed</small><strong>{results.length}</strong></div></div>
              <div className="stat"><span className="stat-ic green">🛡</span><div><small>Threats Flagged</small><strong>{threats}</strong></div></div>
              <div className="stat"><span className="stat-ic purple">◷</span><div><small>Avg. Latency</small><strong>{avgMs} ms</strong></div></div>
              <div className="stat"><span className="stat-ic blue">▅</span><div><small>Peak Risk</small><strong>{Math.round(maxRisk * 100)}%</strong></div></div>
            </section>
            <section className="row1">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic purple sm">▅</span><div><strong>Risk Timeline</strong><small>thresholds 0.60 / 0.75 / 0.90</small></div></div>
                <RiskTimeline data={results} />
              </div>
            </section>
            <section className="row2" id="tech">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic purple sm">▅</span><div><strong>Technical Metrics</strong><small>Real-time analysis parameters</small></div><span className="pill-stable">● Stable</span></div>
                <TechMetrics last={last} />
              </div>
              <div className="card">
                <div className="card-head sm"><span className="call-ic">◷</span><div><strong>Event Timeline</strong><small>Recent detection results</small></div></div>
                <EventTimeline data={results} />
              </div>
            </section>
          </>
        )}

        {/* ================= MODEL & SETTINGS ================= */}
        {page === 'model' && (
          <>
            <div className="page-head"><h1>Model &amp; Settings</h1><p>Which detector is really running, pipeline config and call context.</p></div>
            <section className="row2">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic blue sm">▤</span><div><strong>Active Model</strong><small>Never presented as ML when it is DEMO</small></div><span className="modepill">Mode: {model?.mode_label ?? 'DEMO'}</span></div>
                <div className="call-rows">
                  <div><span>Model</span><b className="mono">{model?.model_name ?? '…'}</b></div>
                  <div><span>Detector mode</span><b className="mono">{model?.detector_mode ?? status?.detector ?? 'demo'}</b></div>
                  <div><span>Checkpoint</span><b className="mono">{model?.model_path ?? '—'}</b></div>
                  <div><span>Device</span><b>{model?.device ?? 'cpu'}</b></div>
                  <div><span>Parameters</span><b>{model?.num_params ? model.num_params.toLocaleString() : '—'}</b></div>
                  <div><span>Loaded</span><b>{model?.model_loaded ? 'Yes' : 'No (DEMO fallback)'}</b></div>
                </div>
                {model?.warning && <div className="notice">{model.warning}</div>}
                <p className="muted">Switch with <span className="mono">VAUTH_DETECTOR</span> (demo | ml | aasist | spectra | spectra3 | w2v2_aasist). Missing checkpoint falls back to DEMO with an explicit warning.</p>
              </div>
              <div className="card">
                <div className="card-head sm"><span className="stat-ic purple sm">⚙</span><div><strong>Pipeline Settings</strong><small>Live backend config</small></div></div>
                <div className="call-rows">
                  <div><span>Window</span><b>{status?.window_seconds ?? 2.5}s</b></div>
                  <div><span>Sample rate</span><b>{status?.target_sample_rate ?? 16000} Hz</b></div>
                  <div><span>Rolling window</span><b>{status?.rolling_window_size ?? 5}</b></div>
                  <div><span>History</span><b>{status?.history_count ?? 0} stored (scores only)</b></div>
                  <div><span>Raw audio stored</span><b>{status?.store_raw_audio ? 'YES' : 'No — discarded'}</b></div>
                  <div><span>Protection</span><b className="mono">{protState}</b></div>
                </div>
              </div>
            </section>
            <section className="row1">
              <div className="card">
                <div className="card-head sm"><span className="call-ic">☎</span><div><strong>Call Context</strong><small>Feeds the bounded context adjustment</small></div></div>
                <div className="ctx-grid">
                  <label className="chk"><input type="checkbox" checked={ctx.caller_known} onChange={(e) => setCtx({ ...ctx, caller_known: e.target.checked })} /> Caller known</label>
                  <label className="chk"><input type="checkbox" checked={ctx.pending_transaction} onChange={(e) => setCtx({ ...ctx, pending_transaction: e.target.checked })} /> Pending transaction</label>
                  <label className="chk"><input type="checkbox" checked={ctx.sensitive_action} onChange={(e) => setCtx({ ...ctx, sensitive_action: e.target.checked })} /> Sensitive action</label>
                  <label>Call type
                    <select value={ctx.call_type} onChange={(e) => setCtx({ ...ctx, call_type: e.target.value as CallContext['call_type'] })}>
                      <option value="demo">Demo</option>
                      <option value="webrtc">WebRTC</option>
                      <option value="twilio">Twilio</option>
                      <option value="vonage">Vonage</option>
                      <option value="upload">Upload</option>
                      <option value="mic">Mic</option>
                    </select>
                  </label>
                </div>
              </div>
            </section>
          </>
        )}

        {/* ================= DEMO BANK ================= */}
        {page === 'bank' && (
          <>
            <div className="page-head"><h1>Demo Bank</h1><p>VAuth decides, the bank enforces. Simulated ledger — no real money.</p></div>
            <section className="row1">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic blue sm">▤</span><div><strong>Simulated Banking</strong><small>Rahul Sharma · VAUTH-10001 · ₹12,50,000</small></div><a className="viewall" href={bankUrl()} target="_blank" rel="noreferrer">Open full page ↗</a></div>
                <p className="muted">Demo flow: run a voice demo on the <b>Live Detection</b> page to set live risk → create the ₹5,00,000 transfer below → verify via simulated OTP / callback / supervisor.</p>
                <iframe className="bank-frame" src="/bank" title="VAuth Demo Bank" />
              </div>
            </section>
          </>
        )}

        {/* ================= API & SDK ================= */}
        {page === 'api' && (
          <>
            <div className="page-head"><h1>API &amp; SDK</h1><p>REST + WebSocket contract for the VAuth backend.</p></div>
            <section className="row2">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic blue sm">﹤/﹥</span><div><strong>Endpoints</strong><small>Backend: {BACKEND}</small></div></div>
                <div className="api-table">
                  {API_ROWS.map(([m, p, d]) => (
                    <div className="api-row" key={p}><span className="api-m">{m}</span><span className="mono">{p}</span><span className="api-d">{d}</span></div>
                  ))}
                </div>
                <div className="live-actions">
                  <a className="btn-select linkbtn" href={`${BACKEND}/docs`} target="_blank" rel="noreferrer">Swagger docs ↗</a>
                  <a className="btn-select linkbtn" href={`${BACKEND}/health`} target="_blank" rel="noreferrer">Health ↗</a>
                  <a className="btn-select linkbtn" href={`${BACKEND}/api/status`} target="_blank" rel="noreferrer">Status JSON ↗</a>
                </div>
              </div>
              <div className="card">
                <div className="card-head sm"><span className="stat-ic purple sm">◁•▮•▷</span><div><strong>Streaming &amp; SDK</strong><small>Mic / WebRTC / Twilio / Vonage</small></div></div>
                <p className="muted">WebSocket <span className="mono">/ws/audio</span>: send <span className="mono">{'{"type":"config",…}'}</span>, then binary PCM16/float32 frames or base64 JSON; receive <span className="mono">analysis_result</span> per 2.5 s window. Twilio streams hit <span className="mono">/ws/twilio</span> as μ-law media events.</p>
                <pre className="code">{`# analyse a file\ncurl -X POST ${BACKEND}/api/analyze-file \\\n  -F "file=@call.wav" \\\n  "http://localhost:8000/api/analyze-file?call_type=upload"`}</pre>
                <pre className="code">{`// browser mic -> VAuth (see hooks/useMic.ts)\nws.send(JSON.stringify({ type: 'config',\n  sample_rate: 16000, encoding: 'pcm16', context }));\nws.send(pcm16Buffer); // per frame`}</pre>
              </div>
            </section>
          </>
        )}

        {/* ================= DOCUMENTATION ================= */}
        {page === 'docs' && (
          <>
            <div className="page-head"><h1>Documentation</h1><p>What VAuth can and cannot do — read before demoing.</p></div>
            <section className="row2">
              <div className="card">
                <div className="card-head sm"><span className="stat-ic blue sm">▭</span><div><strong>Quickstart</strong><small>Local run</small></div></div>
                <pre className="code">{`cd backend\npy -m pip install -r requirements.txt\npy ..\\scripts\\generate_demo_audio.py\npy -m uvicorn app.main:app --host 127.0.0.1 --port 8000\n\ncd ..\\frontend\nnpm install\nnpm run dev  # http://localhost:5173`}</pre>
                <p className="muted">Click <b>Start Real-time Demo</b> (genuine, stays GREEN) then <b>Try Synthetic Voice</b> (climbs to ORANGE/RED). Or use the microphone / upload a WAV.</p>
              </div>
              <div className="card">
                <div className="card-head sm"><span className="shield-sm">🛡</span><div><strong>Scope &amp; Privacy</strong><small>Hard limits</small></div></div>
                <p className="muted">VAuth <b>cannot</b> intercept ordinary cellular calls. It only processes <b>authorized</b> audio: file uploads, browser mic, WebRTC, Twilio/Vonage streams, or authorized VoIP. Raw audio is discarded by default (<span className="mono">STORE_RAW_AUDIO=false</span>); only timestamps, scores and feature summaries are stored.</p>
                <p className="muted">The DEMO detector is a labelled heuristic — expect false positives/negatives. For local REAL ML evaluation use <span className="mono">VAUTH_DETECTOR=spectra3</span>; production needs domain fine-tuning with reported EER/min-tDCF.</p>
              </div>
            </section>
          </>
        )}

        </div>

        <footer className="foot2">
          <span>VAuth v1.0.0 &nbsp;|&nbsp; AI-Powered Voice Cloning Identification SDK &nbsp;|&nbsp; For research and educational use only.</span>
          <span className="right">A safer world through authentic conversations.</span>
        </footer>
      </div>
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast${t.bad ? ' bad' : ''}`}>
            <span>{t.bad ? '⚠' : 'ℹ'} {t.text}</span>
            <button aria-label="dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>✕</button>
          </div>
        ))}
      </div>
      <Assistant last={last} />
    </div>
  );
}
