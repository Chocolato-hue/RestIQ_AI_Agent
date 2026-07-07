import React from 'react';
import Hero from '@/components/landing/Hero';
import Features from '@/components/landing/Features';
import ChatPreview from '@/components/landing/ChatPreview';
import styles from './page.module.css';

export default function Home() {
  return (
    <main className={styles.main}>
      {/* Hero Section */}
      <Hero />

      {/* Feature Grid Section */}
      <Features />

      {/* Interactive Simulator Section */}
      <ChatPreview />

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerContent}>
          <p className={styles.copyright}>
            © {new Date().getFullYear()} RestIQ Sleep Concierge. All rights reserved.
          </p>
          <p className={styles.projectInfo}>
            Built with ❤️ for the Google × Kaggle AI Agents Intensive
          </p>
        </div>
      </footer>
    </main>
  );
}
