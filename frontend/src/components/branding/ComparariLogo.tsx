import type { CSSProperties } from 'react';

interface ComparariLogoProps {
  size?: number;
  showWordmark?: boolean;
  wordmarkClassName?: string;
  className?: string;
  style?: CSSProperties;
}

export function ComparariLogo({
  size = 28,
  showWordmark = true,
  wordmarkClassName,
  className,
  style,
}: ComparariLogoProps) {
  return (
    <span className={className} style={{ display: 'inline-flex', alignItems: 'center', gap: 10, ...style }}>
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <circle cx="25.4" cy="8.6" r="5.8" fill="var(--brand-accent)" />
        <circle cx="25.4" cy="8.6" r="4.2" fill="var(--brand-surface)" />
        <path d="M25.4 8.6L25.4 4.8" stroke="var(--brand-amber)" strokeWidth="1" strokeLinecap="round" />
        <path d="M25.4 8.6L28.7 6.7" stroke="var(--brand-amber)" strokeWidth="1" strokeLinecap="round" />
        <path d="M25.4 8.6L27.9 11.6" stroke="var(--brand-amber)" strokeWidth="1" strokeLinecap="round" />
        <path d="M25.4 8.6L22.1 6.7" stroke="var(--brand-amber)" strokeWidth="1" strokeLinecap="round" />
        <rect x="5" y="7" width="22" height="20" rx="5" fill="var(--brand-surface)" stroke="var(--brand-primary)" strokeWidth="2" />
        <path d="M9 15.5C11.4 14.4 13.8 13.9 16 13.9C18.2 13.9 20.6 14.4 23 15.5V24C20.8 24.8 18.5 25.2 16 25.2C13.5 25.2 11.2 24.8 9 24V15.5Z" fill="var(--brand-primary)" />
      </svg>
      {showWordmark && <span className={wordmarkClassName}>Comparari</span>}
    </span>
  );
}
