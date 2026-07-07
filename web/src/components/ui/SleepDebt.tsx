'use client';

import React from 'react';
import GlassCard from './GlassCard';
import styles from './SleepDebt.module.css';

interface SleepDebtProps {
  duration: number; // in hours
  targetDuration?: number; // target hours
}

export default function SleepDebt({
  duration,
  targetDuration = 8.0,
}: SleepDebtProps) {
  // Sleep bank calculation
  const difference = duration - targetDuration;
  const isDeficit = difference < 0;
  const absoluteDiff = Math.abs(difference);

  // Map progress percent for gauge
  // -3 hours to +3 hours scale
  const range = 6.0; // total hours represented by gauge width
  const percent = Math.max(0, Math.min(100, ((difference + 3) / range) * 100));

  // Visual classes
  let statusClass = styles.neutral;
  let statusLabel = 'Optimized Sleep Bank';
  let message = 'You met your target sleep baseline. Keep maintaining this balance.';

  if (isDeficit) {
    if (absoluteDiff > 2.0) {
      statusClass = styles.critical;
      statusLabel = 'Severe Deficit';
      message = 'Accumulating deep sleep debt. Go to bed 30m earlier tonight to recover.';
    } else {
      statusClass = styles.warning;
      statusLabel = 'Mild Deficit';
      message = 'Slight sleep debt accumulated. Try pushing bedtime slightly earlier.';
    }
  } else if (difference > 1.5) {
    statusClass = styles.oversleep;
    statusLabel = 'Overslept';
    message = 'Sleeping significantly past baseline can disrupt circadian rhythms.';
  }

  return (
    <GlassCard hover className={styles.card}>
      <h3 className={styles.title}>Sleep Debt Tracker</h3>
      <p className={styles.subtitle}>Relative balance against your baseline target.</p>

      <div className={styles.display}>
        <div className={styles.gaugeContainer}>
          <div className={styles.scale}>
            <span>-3h</span>
            <span>Target</span>
            <span>+3h</span>
          </div>
          <div className={styles.track}>
            <div className={styles.midline}></div>
            {/* The cursor position marker */}
            <div
              className={`${styles.marker} ${statusClass}`}
              style={{ left: `${percent}%` }}
            ></div>
          </div>
        </div>

        <div className={styles.valueRow}>
          <span className={styles.label}>Sleep Bank Status:</span>
          <span className={`${styles.badge} ${statusClass}`}>{statusLabel}</span>
        </div>

        <div className={styles.calc}>
          {difference === 0 ? (
            <span className={styles.mainValue}>Balanced Target</span>
          ) : (
            <>
              <span className={styles.mainValue}>{isDeficit ? '-' : '+'}{absoluteDiff.toFixed(1)}h</span>
              <span className={styles.calcLabel}>{isDeficit ? 'Deficit from target' : 'Surplus from target'}</span>
            </>
          )}
        </div>

        <p className={styles.message}>{message}</p>
      </div>
    </GlassCard>
  );
}
