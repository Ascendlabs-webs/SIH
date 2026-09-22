import { useEffect, useMemo, useRef, useState } from 'react';
import ParticleBackground from '../components/ParticleBackground';
import { analyzeFile, bankUrl, fetchStatus, getModelStatus, getProtection, getVonageStatus, protectionAction, resetDemo, startDemo } from '../services/api';
import { useVAuthWS } from '../hooks/useVAuth';
import { useMic } from '../hooks/useMic';
import { RiskGauge } from '../components/RiskGauge';
import { RiskTimeline } from '../components/RiskTimeline';
import { Assistant } from '../components/Assistant';
import { EventTimeline, SignalAnalysis, TechMetrics } from '../components/Panels';
import { AnimatedCounter } from '../components/AnimatedCounter';
import { EmptyState } from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useTheme } from '../components/Theme';
import { levelColor } from '../components/helpers';
import type { AnalysisResult, CallContext, ModelStatus, ProtectionSnapshot, StatusResponse } from '../types';
import type { VonageStatus } from '../services/api';
import '../index.css';

const DEFAULT_CTX: CallContext = {
  caller_known: false,
  pending_transaction: false,
  sensitive_action: true,
  call_type: 'demo',
};

export default function Dashboard() {
  const { theme, toggleTheme } = useTheme();
  const { showToast } = useToast();
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [ctx, setCtx] = useState<CallContext>(DEFAULT_CTX);
  const [mode, setMode] = useState<'DEMO' | 'LIVE'>('DEMO');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [prot, setProt] = useState<ProtectionSnapshot | null>(null);
  const [model, setModel] = useState<ModelStatus | null>(null);
  const [vonage, setVonage] = useState<VonageStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(typeof window !== 'undefined' ? window.innerWidth > 768 : true);
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
    const fetchData = async () => {
      try {
        const [s, m, v] = await Promise.all([
          fetchStatus().catch(() => null),
          getModelStatus().catch(() => null),
          getVonageStatus().catch(() => null),
        ]);
        setStatus(s);
        setModel(m);
        setVonage(v);
      } catch (e) {
        console.error('Failed to fetch status:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
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

  const last: AnalysisResult | null = results.length ? results[results.length - 1] : null;
  const risk = last?.risk_score ?? 0;
  const level = last?.alert_level ?? 'GREEN';
  const color = levelColor(level);

  useEffect(() => {
    if (last && last.alert_level === 'RED') {
      showToast('⚠ HIGH RISK: Synthetic voice detected!', 'error');
    }
  }, [last, showToast]);

  const playDemo = async (scenario: 'real' | 'synthetic' | 'real_speech') => {
    cancelInflight();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    const modelName = model?.model_name ?? 'detector';
    const slow = model && !model.is_demo;
    const t0 = Date.now();
    setNotice(`Analyzing with ${modelName}… (0s)`);
    const tick = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000);
      setNotice(`Analyzing with ${modelName}… (${s}s${slow ? ' — REAL ML takes ~10–25 s on CPU' : ''})`);
    }, 1000);
    timers.current.push(tick);
    const killer = setTimeout(() => ctrl.abort(), 180000);
    timers.current.push(killer);
    try {
      reset();
      await protectionAction('reset').catch(() => undefined);
      const out = await startDemo(scenario, { ...ctx, call_type: 'demo' }, { signal: ctrl.signal });
      clearInterval(tick);
      clearTimeout(killer);
      setMode('DEMO');
      const msg = out.message + (slow ? ' Note: placeholder beeps are out-of-distribution for benchmark models — scores reflect the real model, not the demo script.' : '');
      setNotice(msg);
      showToast(msg, 'info');
      out.results.forEach((r: AnalysisResult, i: number) => {
        timers.current.push(setTimeout(() => pushResult(r), 450 * (i + 1)));
      });
      timers.current.push(setTimeout(refreshProtection, 450 * (out.results.length + 1)));
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        setNotice(ctrl.signal.aborted && Date.now() - t0 >= 180000
          ? 'Analysis timed out after 180 s — the CPU is overloaded. Press Reset and retry.'
          : null);
        return;
      }
      setNotice(e instanceof Error ? e.message : 'Demo failed. Is the backend running? Did you generate demo audio?');
      showToast(e instanceof Error ? e.message : 'Demo failed', 'error');
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setBusy(false);
    }
  };

  const onProtect = async (action: 'request_otp' | 'request_callback' | 'mark_verified' | 'escalate') => {
    try {
      const snap = await protectionAction(action);
      setProt(snap);
      showToast(`Protection action: ${action}`, 'success');
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Protection action failed');
      showToast('Protection action failed', 'error');
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
      const msg = `Analysed ${f.name}: ${r.classification} @ ${Math.round(r.risk_score * 100)}% (${r.alert_level}).`;
      setNotice(msg);
      showToast(msg, 'success');
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Upload failed');
      showToast(e instanceof Error ? e.message : 'Upload failed', 'error');
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
      showToast('Microphone stopped', 'info');
    } else {
      reset();
      setTwilioLive(false);
      await mic.start();
      setMode('LIVE');
      showToast('Microphone started — live analysis active', 'success');
    }
  };

  const toggleTwilioLive = async () => {
    if (twilioLive) {
      stopRecording(false);
      mic.stop();
      setTwilioLive(false);
      setMode('DEMO');
      showToast('Simulated call ended', 'info');
    } else {
      reset();
      setTwilioLive(true);
      await mic.start();
      setMode('LIVE');
      setNotice('Simulated incoming call: your microphone is the caller. Speak and watch VAuth score the call live, exactly as it would score a Twilio phone stream.');
      showToast('Simulated incoming call started', 'warning');
    }
  };

  const downloadWav = (chunks: Int16Array[]) => {
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
  };

  const stopRecording = (download: boolean) => {
    if (!recording) return;
    const chunks = recRef.current ?? [];
    recRef.current = null;
    setRecording(false);
    if (download && chunks.length) {
      downloadWav(chunks);
      showToast('Saved my-voice.wav', 'success');
      setNotice('Saved my-voice.wav — feed it to scripts/simulate_twilio_call.py --file my-voice.wav to run YOUR voice through the Twilio path.');
    }
  };

  const toggleRecord = async () => {
    if (recording) { stopRecording(true); return; }
    if (!mic.active) { reset(); await mic.start(); setMode('LIVE'); }
    recRef.current = [];
    setRecSecs(0);
    setRecording(true);
    showToast('Recording started — speak for ~10s', 'info');
    setNotice('Recording your microphone… speak for ~10 s, then stop. It also streams live to the analyzer.');
    const started = Date.now();
    const tickRec = setInterval(() => {
      const s = Math.round((Date.now() - started) / 1000);
      setRecSecs(s);
      if (s >= 15) { clearInterval(tickRec); stopRecording(true); }
    }, 500);
    timers.current.push(tickRec);
  };

  const protState = prot?.state ?? last?.protection_state ?? 'NORMAL';
  const verified = protState === 'VERIFIED';
  const blocked = protState === 'SECONDARY_VERIFICATION_REQUIRED' || protState === 'BLOCKED';

  const totalDetections = status?.history_count ?? results.length;
  const threatsFlagged = results.filter((r: AnalysisResult) => r.alert_level === 'RED' || r.alert_level === 'ORANGE').length;
  const avgLatency = results.length > 0 ? Math.round(results.reduce((s: number, r: AnalysisResult) => s + r.latency_ms, 0) / results.length) : 0;

  return (
    <div className="dashboard-layout">
      <ParticleBackground />

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <span className="brand-icon">🎙️</span>
            <div>
              <span className="brand-name">VAuth</span>
              <span className="brand-tagline">Real Voices. Real Trust.</span>
            </div>
          </div>
        </div>
        <nav className="sidebar-nav">
          <a className="nav-item active"><span className="nav-icon">🏠</span><span className="nav-label">Dashboard</span></a>
          <a className="nav-item"><span className="nav-icon">🎤</span><span className="nav-label">Live Detection</span></a>
          <a className="nav-item"><span className="nav-icon">⬆️</span><span className="nav-label">Audio Upload</span></a>
          <a className="nav-item"><span className="nav-icon">📞</span><span className="nav-label">Call Monitor</span></a>
          <a className="nav-item"><span className="nav-icon">📊</span><span className="nav-label">Analytics</span></a>
          <a className="nav-item"><span className="nav-icon">⚙️</span><span className="nav-label">Model & Settings</span></a>
          <a className="nav-item" href={bankUrl()} target="_blank" rel="noreferrer"><span className="nav-icon">🏦</span><span className="nav-label">Demo Bank</span></a>
          <a className="nav-item"><span className="nav-icon">💻</span><span className="nav-label">API & SDK</span></a>
          <a className="nav-item"><span className="nav-icon">📚</span><span className="nav-label">Documentation</span></a>
        </nav>
        <div className="sidebar-footer">
          <div className="protect-card">
            <span className="protect-icon">🛡️</span>
            <span className="protect-text">Protect What Matters</span>
          </div>
          <div className="user-profile">
            <div className="user-avatar">S</div>
            <div className="user-info">
              <span className="user-name">School</span>
              <span className="user-role">Admin</span>
            </div>
            <button className="logout-btn">Logout</button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="main-content-wrapper">
        <header className="top-header">
          <div className="header-left">
            <button className="menu-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
            <div className="search-bar">
              <span className="search-icon">🔍</span>
              <input type="text" placeholder="Search calls, recordings, or users..." />
              <kbd className="shortcut">Ctrl K</kbd>
            </div>
          </div>
          <div className="header-right">
            <span className="status-indicator online">
              <span className="status-dot"></span>
              <div>
                <span className="status-label">Connected</span>
                <span className="status-sub">Model: {model?.model_name ?? 'DemoVoiceDetector'}</span>
              </div>
            </span>
            <span className="mode-badge">{model?.mode_label ?? 'DEMO'}</span>
            <button className="theme-toggle" onClick={toggleTheme}>{theme === 'light' ? '🌙' : '☀️'}</button>
            <div className="user-avatar small">S</div>
            <span className="date-display">Sep 22, 2026</span>
          </div>
        </header>

        <main className="dashboard-content">
          <div className="welcome-header">
            <div>
              <h1 className="welcome-title">Welcome to VAuth</h1>
              <p className="welcome-subtitle">Real-time voice authentication to detect AI-generated and cloned voices.</p>
            </div>
            <blockquote className="welcome-quote">"Trust the voice. Stop the imitation." — VAuth</blockquote>
          </div>

          <div className="stats-row">
            <div className="stat-card">
              <span className="stat-icon blue">📊</span>
              <div className="stat-info"><span className="stat-value">{totalDetections}</span><span className="stat-label">Total Detections</span></div>
              <span className="stat-trend up">↑ 12%</span>
            </div>
            <div className="stat-card">
              <span className="stat-icon red">🛡️</span>
              <div className="stat-info"><span className="stat-value">{threatsFlagged}</span><span className="stat-label">Threats Flagged</span></div>
              <span className="stat-trend up">↑ 25%</span>
            </div>
            <div className="stat-card">
              <span className="stat-icon green">⏱️</span>
              <div className="stat-info"><span className="stat-value">{avgLatency} ms</span><span className="stat-label">Avg. Processing</span></div>
              <span className="stat-trend down">↓ 32%</span>
            </div>
            <div className="stat-card">
              <span className="stat-icon purple">🗄️</span>
              <div className="stat-info"><span className="stat-value">Online</span><span className="stat-label">All systems operational</span></div>
              <span className="status-dot large"></span>
            </div>
          </div>

          <div className="main-grid">
            <section className="card live-audio-card">
              <div className="card-header">
                <span className="header-dot red"></span>
                <div><h3 className="card-title">Live Audio Analysis</h3><p className="card-subtitle">Real-time voice authentication and deepfake detection</p></div>
              </div>
              <div className="timer-display">
                <span className="timer">00:00:24</span>
                <span className="listening-status"><span className="status-dot"></span> Listening</span>
              </div>
              <div className="waveform-display">
                {mic.active ? (
                  <div className="waveform-bars">
                    {Array.from({ length: 50 }, (_, i) => (
                      <div key={i} className="wave-bar" style={{ height: `${Math.random() * 80 + 20}%`, animationDelay: `${i * 40}ms` }} />
                    ))}
                  </div>
                ) : (
                  <div className="waveform-placeholder">Microphone inactive — click "Start Listening" to begin</div>
                )}
              </div>
              <div className="audio-controls">
                <button className="btn primary large" disabled={busy} onClick={() => void toggleMic()}>
                  {mic.active ? '⏹ Stop Listening' : '🎤 Start Listening'}
                </button>
                <select className="audio-select"><option>Microphone (Realtek Audio)</option></select>
                <button className="btn ghost">⚙️ Audio Settings</button>
              </div>
              {(notice || lastError || mic.error) && (<div className="notice">{notice ?? lastError ?? mic.error}</div>)}
            </section>

            <section className="card risk-card">
              <div className="card-header">
                <span className="header-dot green"></span>
                <div><h3 className="card-title">Current Risk</h3><p className="card-subtitle">AI-generated voice probability</p></div>
              </div>
              <RiskGauge risk={risk} level={level} classification={last?.classification ?? 'REAL'} />
              <div className="risk-verdict">
                <span className="verdict-label" style={{ color }}>{last?.classification === 'SYNTHETIC' ? 'Synthetic Detected' : 'Likely Genuine'}</span>
                <span className={`risk-pill ${level.toLowerCase()}`}>{level} RISK</span>
              </div>
            </section>

            <section className="card call-info-card">
              <div className="card-header">
                <span className="header-icon">📞</span>
                <div><h3 className="card-title">Call Information</h3><p className="card-subtitle">Details about the current session</p></div>
              </div>
              <div className="info-grid">
                <div className="info-row"><span className="info-label">Call Type</span><span className="info-value">{ctx.call_type}</span></div>
                <div className="info-row"><span className="info-label">Caller ID</span><span className="info-value">{ctx.caller_known ? 'Known' : 'Unknown'}</span></div>
                <div className="info-row"><span className="info-label">Duration</span><span className="info-value">00:00:24</span></div>
                <div className="info-row"><span className="info-label">Sample Rate</span><span className="info-value">16 kHz</span></div>
                <div className="info-row"><span className="info-label">Channels</span><span className="info-value">Mono</span></div>
                <div className="info-row"><span className="info-label">VAD Status</span><span className="info-value"><span className="status-dot"></span> Active</span></div>
                <div className="info-row"><span className="info-label">Backend</span><span className="info-value">{status?.detector?.toUpperCase() ?? 'DEMO'} ({status?.window_seconds ?? 2.5}s window)</span></div>
                <div className="info-row toggle-row">
                  <span className="info-label">Sensitive Action</span>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={ctx.sensitive_action} onChange={(e) => setCtx({ ...ctx, sensitive_action: e.target.checked })} />
                    <span className="toggle-slider"></span>
                  </label>
                </div>
              </div>
            </section>
          </div>

          <div className="bottom-grid">
            <section className="card metrics-card">
              <div className="card-header">
                <span className="header-icon">📈</span>
                <div><h3 className="card-title">Technical Metrics</h3><p className="card-subtitle">Real-time analysis parameters</p></div>
                <span className="status-badge stable">Stable</span>
              </div>
              {last ? <TechMetrics last={last} compact /> : (<EmptyState icon="📈" title="No metrics" message="Analysis results will appear here" />)}
            </section>

            <section className="card timeline-card">
              <div className="card-header">
                <span className="header-icon">🕐</span>
                <div><h3 className="card-title">Event Timeline</h3><p className="card-subtitle">Recent detection results</p></div>
                <a href="#" className="view-all-link">View All</a>
              </div>
              {results.length === 0 ? (<EmptyState icon="📋" title="No events" message="Analysis events will appear here" />) : (<EventTimeline data={results} />)}
            </section>
          </div>

          <div className="action-row">
            <section className="card quick-actions-card">
              <div className="card-header"><span className="header-icon">⚡</span><h3 className="card-title">Quick Actions</h3></div>
              <div className="quick-actions-grid">
                <button className="btn primary" onClick={() => void playDemo('real_speech')}>🎤 Start Real-time Demo</button>
                <button className="btn purple" onClick={() => void playDemo('synthetic')}>🤖 Synthetic Voice</button>
                <label className="btn blue">⬆️ Upload Audio File<input type="file" accept=".wav,audio/wav" hidden onChange={(e) => void onUpload(e.target.files?.[0])} /></label>
                <button className="btn blue" onClick={() => void toggleTwilioLive()}>📞 Simulate Call</button>
              </div>
            </section>

            <section className="card security-card">
              <div className="card-header"><span className="header-icon green">🛡️</span><h3 className="card-title">Security Recommendation</h3></div>
              {last ? (
                <div className="security-content">
                  <div className="security-status">
                    <span className="security-icon green">✓</span>
                    <div>
                      <span className="security-label">{last.classification === 'SYNTHETIC' ? 'Synthetic — verify identity' : 'Likely genuine — proceed normally'}</span>
                      <span className="security-sub">{last.alert_level === 'GREEN' ? 'No immediate action required.' : 'Secondary verification recommended.'}</span>
                    </div>
                  </div>
                  <div className="protect">
                    <div className="card-title sm">Sensitive Action Protection <span className="hint">backend state: {protState}</span></div>
                    <div className="tx">Transaction Request: <strong>₹5,00,000</strong></div>
                    <div className={`tx-status ${blocked ? 'blocked' : 'ok'}`}>
                      Status: {verified ? 'VERIFIED — RELEASED' : blocked ? `${protState} — ACTION HELD` : protState === 'ESCALATED' ? 'ESCALATED TO SUPERVISOR' : level === 'GREEN' ? 'ALLOWED' : 'FLAGGED — REVIEW'}
                    </div>
                    <div className="protect-btns">
                      <button className="btn warn" disabled={!last} onClick={() => void onProtect('request_otp')}>Request OTP</button>
                      <button className="btn warn" disabled={!last} onClick={() => void onProtect('request_callback')}>Request Callback</button>
                      <button className="btn warn" disabled={!last || verified} onClick={() => void onProtect('mark_verified')}>{verified ? '✓ Verified' : 'Mark Verified'}</button>
                      <button className="btn ghost" disabled={!last} onClick={() => void onProtect('escalate')}>Escalate</button>
                    </div>
                  </div>
                </div>
              ) : (<EmptyState icon="🛡️" title="No analysis" message="Run a demo to see recommendations" />)}
            </section>
          </div>

          <footer className="dashboard-footer">
            <span>VAuth v1.0.0 | AI-Powered Voice Cloning Identification SDK | For research and educational use only.</span>
            <span>A safer world through authentic conversations.</span>
          </footer>
        </main>
      </div>
      <Assistant last={last} />
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}
      {/* Mobile Bottom Navigation */}
      <nav className="mobile-bottom-nav">
        <div className="mobile-bottom-nav-inner">
          <button className="mobile-nav-item-bottom active">
            <span className="nav-icon">🏠</span>
            <span>Dashboard</span>
          </button>
          <button className="mobile-nav-item-bottom">
            <span className="nav-icon">🎤</span>
            <span>Live</span>
          </button>
          <button className="mobile-nav-item-bottom">
            <span className="nav-icon">⬆️</span>
            <span>Upload</span>
          </button>
          <button className="mobile-nav-item-bottom">
            <span className="nav-icon">📊</span>
            <span>Analytics</span>
          </button>
          <button className="mobile-nav-item-bottom">
            <span className="nav-icon">⚙️</span>
            <span>Settings</span>
          </button>
        </div>
      </nav>
    </div>
  );
}
