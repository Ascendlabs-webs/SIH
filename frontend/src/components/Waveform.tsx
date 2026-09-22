import { useEffect, useRef } from 'react';

interface WaveformProps {
  active?: boolean;
  color?: string;
  height?: number;
  bars?: number;
}

export function Waveform({ active = false, color = '#0ea5e9', height = 40, bars = 32 }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef(0);
  const barsRef = useRef<number[]>(Array.from({ length: bars }, () => Math.random()));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width = canvas.offsetWidth * 2;
    const h = canvas.height = height * 2;
    ctx.scale(2, 2);

    const draw = () => {
      const cw = w / 2;
      const ch = h / 2;
      ctx.clearRect(0, 0, cw, ch);

      const barWidth = cw / bars;
      const gap = 2;

      for (let i = 0; i < bars; i++) {
        if (active) {
          // Animate toward new random target
          const target = Math.random() * 0.7 + 0.3;
          barsRef.current[i] += (target - barsRef.current[i]) * 0.15;
        } else {
          // Settle to idle
          barsRef.current[i] += (0.15 - barsRef.current[i]) * 0.05;
        }

        const barH = barsRef.current[i] * ch;
        const x = i * barWidth + gap / 2;
        const y = (ch - barH) / 2;

        ctx.fillStyle = color;
        ctx.globalAlpha = active ? 0.8 : 0.3;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth - gap, barH, 2);
        ctx.fill();
      }

      ctx.globalAlpha = 1;
      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [active, color, height, bars]);

  return <canvas ref={canvasRef} style={{ width: '100%', height }} />;
}
