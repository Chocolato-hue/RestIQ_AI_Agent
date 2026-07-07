'use client';

import React, { useEffect, useState } from 'react';

interface AnimatedCounterProps {
  target: number;
  duration?: number; // ms
  suffix?: string;
}

export default function AnimatedCounter({
  target,
  duration = 800,
  suffix = '',
}: AnimatedCounterProps) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTime: number;
    let frameId: number;

    const animate = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      
      // Easing easeOutQuad
      const ease = progress * (2 - progress);
      setCount(Math.round(ease * target));

      if (progress < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [target, duration]);

  return (
    <span>
      {count}
      {suffix}
    </span>
  );
}
