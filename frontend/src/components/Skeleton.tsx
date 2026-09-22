interface SkeletonProps {
  variant?: 'text' | 'title' | 'card' | 'circle' | 'button' | 'chart' | 'row';
  width?: string | number;
  height?: string | number;
  lines?: number;
  animated?: boolean;
}

export function Skeleton({
  variant = 'text',
  width,
  height,
  lines = 1,
  animated = true,
}: SkeletonProps) {
  const baseClass = `skeleton ${animated ? 'animated' : ''} skeleton-${variant}`;

  const style: React.CSSProperties = {
    width: width ?? '100%',
    height: height,
  };

  if (variant === 'card') {
    return (
      <div className={baseClass} style={style}>
        <div className="skeleton-line w-75" />
        <div className="skeleton-line w-50" />
        <div className="skeleton-line w-85" />
        <div className="skeleton-line w-65" />
      </div>
    );
  }

  if (variant === 'chart') {
    return (
      <div className={baseClass} style={style}>
        <div className="skeleton-chart-bars">
          {Array.from({ length: 12 }, (_, i) => (
            <div
              key={i}
              className="skeleton-bar"
              style={{ height: `${Math.random() * 60 + 20}%` }}
            />
          ))}
        </div>
      </div>
    );
  }

  if (variant === 'row') {
    return (
      <div className={baseClass} style={style}>
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className="skeleton-row">
            <span className="skeleton-line w-40" />
            <span className="skeleton-line w-25" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={baseClass} style={style}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton-line" />
      ))}
    </div>
  );
}
