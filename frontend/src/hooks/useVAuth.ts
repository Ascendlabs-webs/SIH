import { useCallback, useEffect, useRef, useState } from 'react';
import type { AnalysisResult, CallContext } from '../types';
import { wsUrl } from '../services/api';

interface WsState {
  connected: boolean;
  results: AnalysisResult[];
  lastError: string | null;
  sendPcm16: (pcm: Int16Array, sampleRate: number) => void;
  reset: () => void;
  clear: () => void;
  pushResult: (r: AnalysisResult) => void;
}

const MAX_POINTS = 120;

export function useVAuthWS(context: CallContext): WsState {
  const [connected, setConnected] = useState(false);
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const ctxRef = useRef(context);
  ctxRef.current = context;

  const pushResult = useCallback((r: AnalysisResult) => {
    setResults((prev) => [...prev.slice(-MAX_POINTS + 1), r]);
  }, []);

  const clear = useCallback(() => setResults([]), []);

  useEffect(() => {
    let dead = false;
    let retry: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (dead) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl('/ws/audio'));
      } catch {
        retry = setTimeout(connect, 2000);
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        if (dead) return;
        setConnected(true);
        setLastError(null);
        ws.send(JSON.stringify({ type: 'config', sample_rate: 16000, encoding: 'pcm16', context: ctxRef.current }));
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'analysis_result' || msg.type === 'result') pushResult(msg as AnalysisResult);
          else if (msg.type === 'error') setLastError(String(msg.detail ?? 'stream error'));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (dead) return;
        setConnected(false);
        wsRef.current = null;
        retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => {
        try { ws.close(); } catch { /* noop */ }
      };
    };
    connect();
    return () => {
      dead = true;
      clearTimeout(retry);
      try { wsRef.current?.close(); } catch { /* noop */ }
    };
  }, [pushResult]);

  const sendPcm16 = useCallback((pcm: Int16Array, sampleRate: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    // Send as binary int16 frame; server buffers into 2.5 s windows.
    const buf = pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength);
    try {
      ws.send(buf);
    } catch {
      /* ignore */
    }
    void sampleRate;
  }, []);

  const reset = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(JSON.stringify({ type: 'reset' })); } catch { /* noop */ }
    }
    setResults([]);
  }, []);

  return { connected, results, lastError, sendPcm16, reset, clear, pushResult };
}
