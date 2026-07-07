import React, { useEffect, useState } from 'react';
import styles from './ScoreRing.module.css';

interface ScoreRingProps {
  score: number;
  size?: number;
  strokeWidth?: number;
  animate?: boolean;
}

export default function ScoreRing({
  score,
  size = 180,
  strokeWidth = 12,
  animate = true,
}: ScoreRingProps) {
  const [animatedScore, setAnimatedScore] = useState(0);

  useEffect(() => {
    if (!animate) {
      setAnimatedScore(score);
      return;
    }
    const duration = 1000; // 1s
    const startTime = performance.now();
    
    let frameId: number;

    const animateCount = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing function (easeOutQuad)
      const ease = progress * (2 - progress);
      setAnimatedScore(Math.round(ease * score));

      if (progress < 1) {
        frameId = requestAnimationFrame(animateCount);
      }
    };

    frameId = requestAnimationFrame(animateCount);
    return () => cancelAnimationFrame(frameId);
  }, [score, animate]);

  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (animatedScore / 100) * circumference;

  // Determine score color class
  const getScoreColorClass = (val: number) => {
    if (val >= 90) return styles.excellent;
    if (val >= 75) return styles.good;
    if (val >= 60) return styles.fair;
    if (val >= 40) return styles.poor;
    return styles.bad;
  };

  return (
    <div className={styles.container} style={{ width: size, height: size }}>
      <svg width={size} height={size} className={styles.svg}>
        {/* Track circle */}
        <circle
          className={styles.track}
          strokeWidth={strokeWidth}
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        {/* Indicator circle */}
        <circle
          className={`${styles.indicator} ${getScoreColorClass(score)}`}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {/* Centered label */}
      <div className={styles.content}>
        <span className={styles.score}>{animatedScore}</span>
        <span className={styles.label}>Sleep Score</span>
      </div>
    </div>
  );
}
