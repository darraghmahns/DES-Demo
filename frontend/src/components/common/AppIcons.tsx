import type { CSSProperties } from 'react';

interface IconProps {
  size?: number;
  stroke?: number;
  style?: CSSProperties;
}

function iconProps(size = 18, stroke = 1.9) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: stroke,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
}

export function IconTransactions({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M7 7h10l2 4v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-6l2-4Z" />
      <path d="M9 11h6" />
      <path d="M9 15h4" />
      <path d="M8 7V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

export function IconComparison({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <rect x="4" y="5" width="6" height="14" rx="1.5" />
      <rect x="14" y="5" width="6" height="14" rx="1.5" />
      <path d="M7 9h0" />
      <path d="M17 9h0" />
      <path d="M7 13h0" />
      <path d="M17 13h0" />
    </svg>
  );
}

export function IconUser({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M12 12a4 4 0 1 0 0-8a4 4 0 0 0 0 8Z" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </svg>
  );
}

export function IconDocuments({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M8 3h6l4 4v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M14 3v4h4" />
      <path d="M9 12h6" />
      <path d="M9 16h6" />
    </svg>
  );
}

export function IconOverview({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="4" rx="1.5" />
      <rect x="13" y="10" width="7" height="10" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
    </svg>
  );
}

export function IconOffers({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M8 7h8" />
      <path d="M8 12h8" />
      <path d="M8 17h5" />
      <path d="M5 7h0" />
      <path d="M5 12h0" />
      <path d="M5 17h0" />
    </svg>
  );
}

export function IconCopy({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function IconRefresh({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M20 11a8 8 0 0 0-14.9-3" />
      <path d="M4 4v4h4" />
      <path d="M4 13a8 8 0 0 0 14.9 3" />
      <path d="M20 20v-4h-4" />
    </svg>
  );
}

export function IconBan({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <circle cx="12" cy="12" r="8" />
      <path d="M8.5 8.5l7 7" />
    </svg>
  );
}

export function IconAutoFill({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M12 3l1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3Z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z" />
    </svg>
  );
}

export function IconImport({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M12 3v10" />
      <path d="m8 9 4 4 4-4" />
      <path d="M5 17v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1" />
    </svg>
  );
}

export function IconLogout({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M14 8V6a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5a2 2 0 0 0 2-2v-2" />
      <path d="M10 12h10" />
      <path d="m17 9 3 3-3 3" />
    </svg>
  );
}

export function IconSun({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2.5" />
      <path d="M12 19.5V22" />
      <path d="M4.9 4.9l1.8 1.8" />
      <path d="m17.3 17.3 1.8 1.8" />
      <path d="M2 12h2.5" />
      <path d="M19.5 12H22" />
      <path d="m4.9 19.1 1.8-1.8" />
      <path d="m17.3 6.7 1.8-1.8" />
    </svg>
  );
}

export function IconMoon({ size = 18, stroke = 1.9, style }: IconProps) {
  return (
    <svg {...iconProps(size, stroke)} style={style}>
      <path d="M12.6 3.5a7.8 7.8 0 1 0 7.9 10.6 8.5 8.5 0 0 1-7.9-10.6Z" />
    </svg>
  );
}
