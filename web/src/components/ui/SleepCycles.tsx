'use client';

import React from 'react';
import GlassCard from './GlassCard';
import styles from './SleepCycles.module.css';

interface SleepCyclesProps {
  duration: number; // in hours
}

export default function SleepCycles({ duration }: SleepCyclesProps) {
  const cycleLengthMin = 90;
  const durationMin = duration * 60;
  const cyclesCount = durationMin / cycleLengthMin;
  const completedCycles = Math.floor(cyclesCount);
  const remainingFraction = cyclesCount - completedCycles;

  // Each 90 min cycle is structured roughly:
  // - Light Sleep: 0 - 30 min (rising/falling wave)
  // - Deep Sleep: 30 - 65 min (trough of the wave)
  // - REM Sleep: 65 - 90 min (crest of the wave)
  // Let's calculate what phase the user woke up in
  const wakeupMin = durationMin % cycleLengthMin;
  
  let phase = 'Light Sleep';
  let phaseNote = 'Smooth transition to waking up.';
  let phaseColor = styles.phaseLight;

  if (wakeupMin >= 30 && wakeupMin < 65) {
    phase = 'Deep NREM Sleep';
    phaseNote = 'Waking up here can cause severe grogginess (sleep inertia).';
    phaseColor = styles.phaseDeep;
  } else if (wakeupMin >= 65) {
    phase = 'REM Dream Sleep';
    phaseNote = 'Waking up from active dreaming phase.';
    phaseColor = styles.phaseRem;
  }

  // Generate SVG path for a wave representing cycles
  // Let's render 5 cycles as a sinusoidal path
  const svgWidth = 500;
  const svgHeight = 60;
  const pathPoints = [];
  
  // Plotting a sine-like wave representing NREM/REM cycles
  for (let x = 0; x <= svgWidth; x++) {
    // Normalizing x to cycles
    const cycleX = (x / svgWidth) * Math.max(5, completedCycles + 1);
    const rad = cycleX * 2 * Math.PI;
    
    // Wave shape: deeper troughs (deep sleep), higher crests (REM)
    const y = svgHeight / 2 + Math.sin(rad) * 20 - Math.cos(rad * 2) * 5;
    pathPoints.push(`${x},${y}`);
  }
  
  const wavePath = `M ${pathPoints.join(' L ')}`;

  // Find the exact wake-up point on the wave path
  const wakeupX = (durationMin / (Math.max(5, completedCycles + 1) * cycleLengthMin)) * svgWidth;
  const wakeupCycleRad = (durationMin / cycleLengthMin) * 2 * Math.PI;
  const wakeupY = svgHeight / 2 + Math.sin(wakeupCycleRad) * 20 - Math.cos(wakeupCycleRad * 2) * 5;

  return (
    <GlassCard hover className={styles.card}>
      <h3 className={styles.title}>Circadian Sleep Cycles</h3>
      <p className={styles.subtitle}>Analyzing 90-minute NREM/REM brainwave cycles.</p>

      <div className={styles.metricsGrid}>
        <div className={styles.metric}>
          <span className={styles.value}>{completedCycles}</span>
          <span className={styles.label}>Completed Cycles</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.value}>{(duration / 1.5).toFixed(1)}</span>
          <span className={styles.label}>Cycle Efficiency</span>
        </div>
      </div>

      {/* Cycle Wave Visualization */}
      <div className={styles.waveContainer}>
        <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className={styles.svg}>
          {/* Base midline */}
          <line x1={0} y1={svgHeight / 2} x2={svgWidth} y2={svgHeight / 2} className={styles.midline} />
          {/* Wave Path */}
          <path d={wavePath} className={styles.wave} />
          {/* Wakeup point indicator */}
          {wakeupX <= svgWidth && (
            <g className={styles.indicatorGroup}>
              <circle cx={wakeupX} cy={wakeupY} r={6} className={styles.wakePoint} />
              <circle cx={wakeupX} cy={wakeupY} r={12} className={styles.wakePointPulse} />
              <line x1={wakeupX} y1={0} x2={wakeupX} y2={svgHeight} className={styles.wakeLine} />
            </g>
          )}
        </svg>
        <div className={styles.waveLabels}>
          <span>Sleep Start</span>
          <span>Wake Up Point</span>
        </div>
      </div>

      {/* Sleep Phase Insight */}
      <div className={`${styles.insight} ${phaseColor}`}>
        <div className={styles.insightHeader}>
          <span className={styles.phaseLabel}>Woke Up In:</span>
          <span className={styles.phaseValue}>{phase}</span>
        </div>
        <p className={styles.phaseNote}>{phaseNote}</p>
      </div>
    </GlassCard>
  );
}
