'use client';

import React from 'react';
import styles from './WeeklyInsightCard.module.css';

interface WeeklyInsightCardProps {
  avgScore: number;
  avgDuration: number;
  streak: number;
  verdict: string;
}

export default function WeeklyInsightCard({
  avgScore,
  avgDuration,
  streak,
  verdict,
}: WeeklyInsightCardProps) {
  const getVerdictLabel = (v: string) => {
    switch (v) {
      case 'EXCELLENT':
        return 'Excellent';
      case 'ON_TRACK':
        return 'On Track';
      case 'IMPROVING':
        return 'Improving';
      case 'NEEDS_ATTENTION':
        return 'Needs Attention';
      default:
        return v;
    }
  };

  const getVerdictClass = (v: string) => {
    switch (v) {
      case 'EXCELLENT':
        return styles.excellent;
      case 'ON_TRACK':
        return styles.good;
      case 'IMPROVING':
        return styles.fair;
      case 'NEEDS_ATTENTION':
        return styles.bad;
      default:
        return styles.neutral;
    }
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.title}>Weekly Report Overview</span>
        <span className={`${styles.badge} ${getVerdictClass(verdict)}`}>
          {getVerdictLabel(verdict)}
        </span>
      </div>

      <div className={styles.metrics}>
        <div className={styles.metric}>
          <span className={styles.metricVal}>{Math.round(avgScore)}/100</span>
          <span className={styles.metricLbl}>Avg Score</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricVal}>{avgDuration.toFixed(1)}h</span>
          <span className={styles.metricLbl}>Avg Duration</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricVal}>{streak} days</span>
          <span className={styles.metricLbl}>Check-ins</span>
        </div>
      </div>
    </div>
  );
}
