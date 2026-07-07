'use client';

import React from 'react';
import styles from './CoachingTip.module.css';

interface CoachingTipProps {
  tip: string;
  category?: 'caffeine' | 'screen' | 'exercise' | 'duration' | 'general';
}

const config = {
  caffeine: { icon: '☕', label: 'Caffeine Advice', class: styles.caffeine },
  screen: { icon: '📱', label: 'Screen Timing', class: styles.screen },
  exercise: { icon: '🏋️', label: 'Physical Activity', class: styles.exercise },
  duration: { icon: '⏳', label: 'Duration Target', class: styles.duration },
  general: { icon: '💡', label: 'Daily Tip', class: styles.general },
};

export default function CoachingTip({ tip, category = 'general' }: CoachingTipProps) {
  const c = config[category] || config.general;

  return (
    <div className={`${styles.card} ${c.class}`}>
      <div className={styles.header}>
        <span className={styles.icon}>{c.icon}</span>
        <span className={styles.label}>{c.label}</span>
      </div>
      <p className={styles.tipText}>{tip}</p>
    </div>
  );
}
