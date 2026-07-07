'use client';

import React, { useState } from 'react';
import styles from './QuickCheckinForm.module.css';

interface QuickCheckinFormProps {
  onSubmit: (data: {
    bedtime: string;
    wakeTime: string;
    sleepQuality: string;
    moodOnWake: string;
    notes?: string;
  }) => void;
}

export default function QuickCheckinForm({ onSubmit }: QuickCheckinFormProps) {
  const [bedtime, setBedtime] = useState('23:00');
  const [wakeTime, setWakeTime] = useState('07:00');
  const [sleepQuality, setSleepQuality] = useState('GOOD');
  const [moodOnWake, setMoodOnWake] = useState('GOOD');
  const [notes, setNotes] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ bedtime, wakeTime, sleepQuality, moodOnWake, notes });
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className={styles.card}>
        <div className={styles.success}>
          <span>✓</span> Check-in parameters submitted to coach
        </div>
      </div>
    );
  }

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      <h4 className={styles.title}>Fast Sleep check-in</h4>

      <div className={styles.row}>
        <div className={styles.field}>
          <label className={styles.label}>Bedtime</label>
          <input
            type="text"
            className={styles.input}
            value={bedtime}
            onChange={(e) => setBedtime(e.target.value)}
            placeholder="23:00"
            required
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Wake Time</label>
          <input
            type="text"
            className={styles.input}
            value={wakeTime}
            onChange={(e) => setWakeTime(e.target.value)}
            placeholder="07:00"
            required
          />
        </div>
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label className={styles.label}>Quality</label>
          <select
            className={styles.select}
            value={sleepQuality}
            onChange={(e) => setSleepQuality(e.target.value)}
          >
            <option value="POOR">Poor</option>
            <option value="FAIR">Fair</option>
            <option value="GOOD">Good</option>
            <option value="EXCELLENT">Excellent</option>
          </select>
        </div>
        <div className={styles.field}>
          <label className={styles.label}>Mood</label>
          <select
            className={styles.select}
            value={moodOnWake}
            onChange={(e) => setMoodOnWake(e.target.value)}
          >
            <option value="TERRIBLE">Terrible</option>
            <option value="TIRED">Tired</option>
            <option value="OKAY">Okay</option>
            <option value="GOOD">Good</option>
            <option value="GREAT">Great</option>
          </select>
        </div>
      </div>

      <div className={styles.field}>
        <label className={styles.label}>Notes</label>
        <textarea
          className={styles.textarea}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="e.g. coffee late, phone scrolling..."
          rows={2}
        />
      </div>

      <button type="submit" className={styles.submitBtn}>
        Submit to Concierge
      </button>
    </form>
  );
}
