import React from 'react';
import GradientButton from '../ui/GradientButton';
import styles from './Hero.module.css';

export default function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.orbs}>
        <div className={`${styles.orb} ${styles.orb1}`} />
        <div className={`${styles.orb} ${styles.orb2}`} />
      </div>
      
      <div className={styles.content}>
        <div className={styles.badgeContainer}>
          <span className={styles.badge}>Introducing RestIQ WebUI</span>
        </div>
        
        <h1 className={styles.title}>
          Your Personal <span className={styles.gradientText}>AI Sleep Concierge</span>
        </h1>
        
        <p className={styles.description}>
          Track your sleep, understand your habits, and build healthier routines with an active team of collaborative AI agents. Custom designed for the ultimate agent-user experience.
        </p>
        
        <div className={styles.ctaGroup}>
          <GradientButton href="/dashboard" variant="primary" size="lg">
            Enter Dashboard 🌙
          </GradientButton>
          <GradientButton href="#features" variant="glass" size="lg">
            Learn More
          </GradientButton>
        </div>
        
        <div className={styles.techText}>
          Powered by <span className={styles.highlight}>Google ADK</span> &amp; <span className={styles.highlight}>CopilotKit</span>
        </div>
      </div>
    </section>
  );
}
