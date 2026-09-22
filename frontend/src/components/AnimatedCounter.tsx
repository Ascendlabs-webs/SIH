import { useEffect, useRef } from 'react';

export function AnimatedCounter({ value, duration = 800 }: { value: number; duration?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const from = useRef(value);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const start = from.current;
    const diff = value - start;
    const startTime = performance.now();

    const tick = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round((start + diff * eased) * 100) / 100;
      el.textContent = `${Math.round(current * 100)}%`;
      if (progress < 1) requestAnimationFrame(tick);
      else from.current = value;
    };

    requestAnimationFrame(tick);
  }, [value, duration]);

  return <div ref={ref}>{Math.round(value * 100)}%</div>;
}
