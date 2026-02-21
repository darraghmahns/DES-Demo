/** Circular/bar completion percentage indicator. */

interface CompletionIndicatorProps {
  percentage: number;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function CompletionIndicator({ percentage, label, size = 'md' }: CompletionIndicatorProps) {
  const clamped = Math.min(100, Math.max(0, percentage));
  const color = clamped >= 80 ? '#4caf50' : clamped >= 50 ? '#ff9800' : '#f44336';

  const sizeClass = `completion-indicator completion-${size}`;

  return (
    <div className={sizeClass}>
      <div className="completion-bar-track">
        <div
          className="completion-bar-fill"
          style={{ width: `${clamped}%`, backgroundColor: color }}
        />
      </div>
      <span className="completion-label">
        {label && <span className="completion-label-text">{label}</span>}
        <span className="completion-pct" style={{ color }}>{Math.round(clamped)}%</span>
      </span>
    </div>
  );
}
