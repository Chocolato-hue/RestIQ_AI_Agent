'use client';

import React, { useEffect, useState } from 'react';
import GlassCard from '../ui/GlassCard';
import styles from './ChatPreview.module.css';

interface Message {
  role: 'bot' | 'user';
  content: string;
  delay: number;
}

const mockTranscript: Message[] = [
  {
    role: 'bot',
    content: "Welcome back! 🌙 How did you sleep last night? Let me know bedtime, wake time, and how you feel.",
    delay: 500,
  },
  {
    role: 'user',
    content: "Slept around 11:30 PM, woke up at 7:00 AM. Woke up once, but felt pretty refreshed. Did not drink coffee late.",
    delay: 2000,
  },
  {
    role: 'bot',
    content: "Got it! Bedtime 11:30 PM, wake time 7:00 AM (7.5 hours duration). Let me save that check-in.",
    delay: 3800,
  },
  {
    role: 'bot',
    content: "⭐ Sleep Score: 84/100 (Good)\nTonight's recommended bedtime: 10:45 PM.\nGoal: Move bedtime 15m earlier to reduce mild sleep debt.",
    delay: 5000,
  },
];

export default function ChatPreview() {
  const [messages, setMessages] = useState<Message[]>([]);

  useEffect(() => {
    const timers = mockTranscript.map((msg) => {
      return setTimeout(() => {
        setMessages((prev) => [...prev, msg]);
      }, msg.delay);
    });

    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, []);

  return (
    <section className={styles.section}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h2 className={styles.title}>Conversational Sleep Tracking</h2>
          <p className={styles.subtitle}>
            Say goodbye to rigid grids and checkboxes. Check in with RestIQ naturally in your own words, and let the agents handle structural translation.
          </p>
        </div>

        <GlassCard className={styles.chatWindow}>
          <div className={styles.chatHeader}>
            <div className={styles.avatar}>🌙</div>
            <div>
              <div className={styles.botName}>RestIQ Sleep Coach</div>
              <div className={styles.status}>Active Agent</div>
            </div>
          </div>

          <div className={styles.messageArea}>
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`${styles.messageRow} ${
                  msg.role === 'user' ? styles.userRow : styles.botRow
                } animate-fade-in`}
              >
                <div
                  className={`${styles.bubble} ${
                    msg.role === 'user' ? styles.userBubble : styles.botBubble
                  }`}
                >
                  {msg.content.split('\n').map((line, lIdx) => (
                    <p key={lIdx}>{line}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className={styles.inputArea}>
            <div className={styles.fakeInput}>
              Type your reply...
            </div>
            <button className={styles.sendBtn} disabled>Send</button>
          </div>
        </GlassCard>
      </div>
    </section>
  );
}
