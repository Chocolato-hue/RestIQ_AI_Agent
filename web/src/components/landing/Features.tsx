import React from 'react';
import GlassCard from '../ui/GlassCard';
import styles from './Features.module.css';

export default function Features() {
  const items = [
    {
      icon: '🤖',
      title: 'AI-Powered Analysis',
      description: 'A dedicated team of specialized agents analyzes sleep quality, bedtime consistency, and wake-up behaviors to pinpoint optimization areas.',
      glow: 'indigo' as const,
    },
    {
      icon: '🌙',
      title: 'Smart Recommendations',
      description: 'Your sleep concierge dynamically calculates circadian bedtime recommendations and adjusts targets gradually to avoid sleep debt.',
      glow: 'emerald' as const,
    },
    {
      icon: '📊',
      title: 'Weekly Intelligence',
      description: 'Unlock comprehensive health reports, pattern correlation graphs, and personalized milestones that reward consistency.',
      glow: 'amber' as const,
    },
  ];

  return (
    <section id="features" className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>Designed for Health Optimization</h2>
        <p className={styles.subtitle}>
          RestIQ leverages collaborative agents to parse natural inputs, calculate circadian variables, and enforce habit-forming consistency.
        </p>
      </div>

      <div className={styles.grid}>
        {items.map((item, idx) => (
          <GlassCard key={idx} hover glow={item.glow} className={styles.card}>
            <div className={styles.icon}>{item.icon}</div>
            <h3 className={styles.cardTitle}>{item.title}</h3>
            <p className={styles.cardDesc}>{item.description}</p>
          </GlassCard>
        ))}
      </div>
    </section>
  );
}
