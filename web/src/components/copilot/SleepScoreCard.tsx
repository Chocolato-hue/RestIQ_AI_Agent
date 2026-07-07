'use client';

import React from 'react';
import styles from './SleepScoreCard.module.css';

interface SleepScoreCardProps {
  score: number;
  duration: number;
  bedtime: string;
  wakeTime: string;
  quality: string;
  coachRemarks?: string;
}

export default function SleepScoreCard({
  score,
  duration,
  bedtime,
  wakeTime,
  quality,
  coachRemarks,
}: SleepScoreCardProps) {
  const getScoreColor = (val: number) => {
    if (val >= 90) return styles.excellent;
    if (val >= 75) return styles.good;
    if (val >= 60) return styles.fair;
    return styles.poor;
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.title}>Sleep Record Logged</span>
        <span className={`${styles.badge} ${getScoreColor(score)}`}>
          Score: {score}
        </span>
      </div>

      <div className={styles.metrics}>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Duration</span>
          <span className={styles.metricValue}>{duration}h</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Schedule</span>
          <span className={styles.metricValue}>{bedtime} - {wakeTime}</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Quality</span>
          <span className={styles.metricValue}>{quality}</span>
        </div>
      </div>

      {coachRemarks && (
        <div className={styles.coaching}>
          <div className={styles.coachingHeader}>
            <span className={styles.coachingIcon}>🏋️</span>
            <span className={styles.coachingTitle}>Coach Advice</span>
          </div>
          <p className={styles.coachingText}>{coachRemarks}</p>
        </div>
      )}
    </div>
  );
}
