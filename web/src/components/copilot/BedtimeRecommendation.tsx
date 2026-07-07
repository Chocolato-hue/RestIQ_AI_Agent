'use client';

import React from 'react';
import styles from './BedtimeRecommendation.module.css';

interface BedtimeRecommendationProps {
  bedtime: string;
  windDownTime?: string;
  sleepDuration?: number;
}

export default function BedtimeRecommendation({
  bedtime,
  windDownTime = '22:15',
  sleepDuration = 8.0,
}: BedtimeRecommendationProps) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.moon}>🌙</span>
        <div className={styles.headerText}>
          <span className={styles.title}>Recommended Bedtime</span>
          <span className={styles.subtitle}>Tonight&apos;s Sleep Schedule</span>
        </div>
      </div>

      <div className={styles.mainTime}>
        <span className={styles.time}>{bedtime}</span>
        <span className={styles.ampm}>{parseInt(bedtime.split(':')[0]) >= 12 ? 'PM' : 'AM'}</span>
      </div>

      <div className={styles.details}>
        <div className={styles.detail}>
          <span className={styles.detailLabel}>Wind-down starts</span>
          <span className={styles.detailValue}>{windDownTime}</span>
        </div>
        <div className={styles.detail}>
          <span className={styles.detailLabel}>Target sleep</span>
          <span className={styles.detailValue}>{sleepDuration} hrs</span>
        </div>
      </div>
    </div>
  );
}
