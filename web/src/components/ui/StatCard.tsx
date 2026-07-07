import React from 'react';
import GlassCard from './GlassCard';
import styles from './StatCard.module.css';

export interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  subValue?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendText?: string;
}

export default function StatCard({
  icon,
  label,
  value,
  subValue,
  trend,
  trendText,
}: StatCardProps) {
  return (
    <GlassCard hover className={styles.card}>
      <div className={styles.header}>
        <div className={styles.iconContainer}>{icon}</div>
        {trend && (
          <div className={`${styles.trend} ${styles[trend]}`}>
            {trend === 'up' && '↑'}
            {trend === 'down' && '↓'}
            {trend === 'neutral' && '•'}
            {trendText && <span className={styles.trendText}>{trendText}</span>}
          </div>
        )}
      </div>
      <div className={styles.content}>
        <span className={styles.label}>{label}</span>
        <h3 className={styles.value}>{value}</h3>
        {subValue && <span className={styles.subValue}>{subValue}</span>}
      </div>
    </GlassCard>
  );
}
