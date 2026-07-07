import React from 'react';
import styles from './GlassCard.module.css';

export type GlowColor = 'indigo' | 'emerald' | 'amber' | 'red';

export interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  /** Enable hover lift effect */
  hover?: boolean;
  /** Glow color on hover */
  glow?: GlowColor;
  /** Additional inline styles */
  style?: React.CSSProperties;
}

const glowMap: Record<GlowColor, string> = {
  indigo: styles.glowIndigo,
  emerald: styles.glowEmerald,
  amber: styles.glowAmber,
  red: styles.glowRed,
};

export default function GlassCard({
  children,
  className = '',
  hover = false,
  glow,
  style,
}: GlassCardProps) {
  const classes = [
    styles.card,
    hover ? styles.hoverable : '',
    glow ? glowMap[glow] : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={classes} style={style}>
      {children}
    </div>
  );
}
