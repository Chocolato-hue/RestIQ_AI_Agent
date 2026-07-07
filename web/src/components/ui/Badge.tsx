import React from 'react';
import styles from './Badge.module.css';

export type BadgeVariant = 'excellent' | 'good' | 'fair' | 'poor' | 'bad' | 'info' | 'neutral';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export default function Badge({ children, variant = 'neutral', className = '' }: BadgeProps) {
  const classes = [styles.badge, styles[variant], className].filter(Boolean).join(' ');

  return <span className={classes}>{children}</span>;
}
