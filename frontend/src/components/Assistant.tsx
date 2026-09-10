import React, { useRef, useState } from 'react';
import { askAssistant } from '../services/api';
import type { AnalysisResult } from '../types';

interface Msg { from: 'you' | 'bot'; text: string }

const CHIPS = [
  'What is my current risk?',
  'What should I do next?',
  'Which model is running?',
  'How do I run the bank demo?',
];

export function Assistant({ last }: { last: AnalysisResult | null }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    { from: 'bot', text: 'Hi — I can read the live VAuth state. Ask about current risk, next actions, the active model, or any demo.' },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setMsgs((m) => [...m, { from: 'you', text: q }]);
    setInput('');
    setBusy(true);
    // Send the asker's own dashboard reading so the answer matches the gauge,
    // even when the server history holds windows from other sessions.
    const state = last
      ? { risk_score: last.risk_score, alert_level: last.alert_level, classification: last.classification }
      : null;
    try {
      const r = await askAssistant(q, state);
      setMsgs((m) => [...m, { from: 'bot', text: r.answer }]);
    } catch {
      setMsgs((m) => [...m, { from: 'bot', text: 'Backend unreachable — is the API running?' }]);
    } finally {
      setBusy(false);
      setTimeout(() => boxRef.current?.scrollTo({ top: 99999 }), 50);
    }
  };

  return (
    <>
      <button className="chat-fab" onClick={() => setOpen((o) => !o)} title="VAuth assistant">
        {open ? '✕' : '◉ Assistant'}
      </button>
      {open && (
        <div className="chat-panel">
          <div className="chat-head">VAuth Assistant <span>live backend state</span></div>
          <div className="chat-box" ref={boxRef}>
            {msgs.map((m, i) => (
              <div key={i} className={`chat-msg ${m.from}`}>{m.text}</div>
            ))}
            {busy && <div className="chat-msg bot">…</div>}
          </div>
          <div className="chat-chips">
            {CHIPS.map((c) => (
              <button key={c} onClick={() => void send(c)}>{c}</button>
            ))}
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void send(input); }}
              placeholder="Ask about risk, actions, model…"
            />
            <button onClick={() => void send(input)}>➤</button>
          </div>
        </div>
      )}
    </>
  );
}
