'use client';

import React, { useEffect, useState } from 'react';
import { useCopilotReadable, useCopilotAction } from '@copilotkit/react-core';
import { useCopilotChatSuggestions } from '@copilotkit/react-ui';
import GlassCard from '@/components/ui/GlassCard';
import ScoreRing from '@/components/ui/ScoreRing';
import StatCard from '@/components/ui/StatCard';
import TrendChart from '@/components/ui/TrendChart';
import Badge from '@/components/ui/Badge';
import Skeleton from '@/components/ui/Skeleton';
import { fetchHistory, fetchLatest, fetchAnalysis, fetchPlan } from '@/lib/api';
import { SleepEntry, SleepAnalysis, PlanAdjustment } from '@/lib/types';
import SleepCycles from '@/components/ui/SleepCycles';
import SleepDebt from '@/components/ui/SleepDebt';
import styles from './page.module.css';

export default function Dashboard() {
  const userId = 'demo-user'; // Default demo user
  const [history, setHistory] = useState<SleepEntry[]>([]);
  const [latestEntry, setLatestEntry] = useState<SleepEntry | null>(null);
  const [analysis, setAnalysis] = useState<SleepAnalysis | null>(null);
  const [plan, setPlan] = useState<PlanAdjustment | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [histData, latestData, analysisData, planData] = await Promise.all([
        fetchHistory(userId, 7),
        fetchLatest(userId),
        fetchAnalysis(userId, 7),
        fetchPlan(userId),
      ]);
      setHistory(histData.entries || []);
      setLatestEntry(latestData);
      setAnalysis(analysisData);
      setPlan(planData);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // ── CopilotKit Context (AX) ──
  useCopilotReadable({
    description: 'Current user sleep history for the last 7 days.',
    value: history,
  });

  useCopilotReadable({
    description: 'Latest logged sleep entry details.',
    value: latestEntry,
  });

  useCopilotReadable({
    description: 'Calculated patterns and recommendations from sleep analysis.',
    value: analysis,
  });

  useCopilotReadable({
    description: 'Current sleep goal and bedtime plan status.',
    value: plan,
  });

  useCopilotReadable({
    description: 'Sleep cycles completed last night.',
    value: latestEntry ? Math.floor((latestEntry.sleep_duration * 60) / 90) : 0,
  });

  useCopilotReadable({
    description: 'Sleep bank deficit or surplus in hours relative to 8h target.',
    value: latestEntry ? latestEntry.sleep_duration - 8.0 : 0,
  });

  // ── CopilotKit Actions (AX) ──
  useCopilotAction({
    name: 'highlightMetric',
    description: 'Highlight a specific metric on the dashboard to draw user attention.',
    parameters: [
      {
        name: 'metric',
        type: 'string',
        description: 'The metric to highlight: score, duration, wakeups, streak, plan',
        required: true,
      },
    ],
    handler: async ({ metric }) => {
      setActiveHighlight(metric);
      setTimeout(() => setActiveHighlight(null), 5000); // Clear highlight after 5s
    },
  });

  useCopilotAction({
    name: 'refreshDashboard',
    description: 'Reload dashboard sleep data from the database.',
    handler: async () => {
      await loadData();
    },
  });

  // ── CopilotKit Suggestions (AX) ──
  useCopilotChatSuggestions(
    {
      instructions: `Suggest items like: "Log last night's sleep", "What is my recommended bedtime?", "Analyze my sleep patterns". Customize suggestions based on the user's latest sleep score of ${latestEntry?.score || 'none'} and status.`,
    },
    [latestEntry]
  );

  // Format Recharts data
  const chartData = [...history]
    .reverse()
    .map((entry) => {
      const date = new Date(entry.date);
      const dayName = date.toLocaleDateString('en-US', { weekday: 'short' });
      return {
        day: dayName,
        score: entry.score,
      };
    });

  const getBadgeVariant = (score: number) => {
    if (score >= 90) return 'excellent';
    if (score >= 75) return 'good';
    if (score >= 60) return 'fair';
    if (score >= 40) return 'poor';
    return 'bad';
  };

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.loadingHeader}>
          <Skeleton width="200px" height="32px" />
          <Skeleton width="120px" height="20px" />
        </div>
        <div className={styles.statsRow}>
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} width="100%" height="120px" />
          ))}
        </div>
        <div className={styles.mainGrid}>
          <Skeleton width="100%" height="340px" />
          <Skeleton width="100%" height="340px" />
        </div>
      </div>
    );
  }

  const score = latestEntry?.score || 0;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Sleep Intelligence</h1>
          <p className={styles.subtitle}>Welcome back! Here is your current sleep profile.</p>
        </div>
        {latestEntry && (
          <Badge variant={getBadgeVariant(score)}>
            Latest Score: {score}/100
          </Badge>
        )}
      </header>

      {/* Stats Cards Row */}
      <div className={styles.statsRow}>
        <div className={activeHighlight === 'duration' ? styles.highlightedCard : ''}>
          <StatCard
            icon="🛌"
            label="Avg Duration"
            value={analysis ? `${analysis.average_duration.toFixed(1)} hrs` : '--'}
            subValue="Ideal range: 7–9 hrs"
          />
        </div>
        <div className={activeHighlight === 'wakeups' ? styles.highlightedCard : ''}>
          <StatCard
            icon="🔔"
            label="Avg Wake-ups"
            value={analysis ? `${analysis.average_wake_ups.toFixed(1)}` : '--'}
            subValue="Interruptions per night"
          />
        </div>
        <div className={activeHighlight === 'streak' ? styles.highlightedCard : ''}>
          <StatCard
            icon="🔥"
            label="Check-in Streak"
            value={analysis ? `${analysis.streak_days} days` : '--'}
            subValue="Consistency is key"
          />
        </div>
        <div className={activeHighlight === 'plan' ? styles.highlightedCard : ''}>
          <StatCard
            icon="🎯"
            label="Target Bedtime"
            value={plan?.new_target_bedtime || '23:00'}
            subValue={plan ? `Status: ${plan.status}` : 'Plan Active'}
          />
        </div>
      </div>

      {/* Main Grid */}
      <div className={styles.mainGrid}>
        {/* Sleep Score Card */}
        <GlassCard
          className={`${styles.scoreCard} ${
            activeHighlight === 'score' ? styles.highlightedCard : ''
          }`}
        >
          <h3 className={styles.cardTitle}>Latest Night Sleep</h3>
          <div className={styles.scoreContainer}>
            <ScoreRing score={score} />
          </div>
          {latestEntry && (
            <div className={styles.latestDetails}>
              <p className={styles.latestNotes}>
                &ldquo;{latestEntry.notes || 'No description provided.'}&rdquo;
              </p>
              <div className={styles.latestTags}>
                <Badge variant={latestEntry.caffeine_after_2pm ? 'bad' : 'neutral'}>
                  {latestEntry.caffeine_after_2pm ? '☕ Caffeine after 2PM' : '☕ No late caffeine'}
                </Badge>
                <Badge variant={latestEntry.screen_time_before_bed ? 'bad' : 'excellent'}>
                  {latestEntry.screen_time_before_bed ? '📱 Bedtime screen use' : '📱 No screen before bed'}
                </Badge>
                {latestEntry.exercise_today && (
                  <Badge variant="good">
                    🏋️ Exercised
                  </Badge>
                )}
              </div>
            </div>
          )}
        </GlassCard>

        {/* Trend Area Chart */}
        <GlassCard className={styles.chartCard}>
          <div className={styles.chartHeader}>
            <h3 className={styles.cardTitle}>7-Day Sleep Score Trend</h3>
            <span className={styles.chartLegend}>Score</span>
          </div>
          {chartData.length > 0 ? (
            <TrendChart data={chartData} />
          ) : (
            <div className={styles.emptyChart}>Log sleep entries to visualize weekly trends.</div>
          )}
        </GlassCard>
      </div>

      {/* Circadian Analysis Widgets */}
      {latestEntry && (
        <div className={styles.circadianGrid}>
          <SleepCycles duration={latestEntry.sleep_duration} />
          <SleepDebt duration={latestEntry.sleep_duration} />
        </div>
      )}

      {/* Coaching & Insights */}
      {analysis && (
        <div className={styles.coachingGrid}>
          <GlassCard className={styles.coachingCard}>
            <h3 className={styles.cardTitle}>🌙 Today&apos;s Sleep Coach Insights</h3>
            <div className={styles.insightsList}>
              {analysis.recommendations.slice(0, 3).map((rec, i) => (
                <div key={i} className={styles.insightItem}>
                  <span className={styles.insightIcon}>🎯</span>
                  <p className={styles.insightText}>{rec}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className={styles.patternsCard}>
            <h3 className={styles.cardTitle}>🧠 Sleep Patterns Detected</h3>
            <div className={styles.patternsList}>
              {analysis.patterns_detected.length > 0 ? (
                analysis.patterns_detected.map((pattern, i) => (
                  <div key={i} className={styles.patternTag}>
                    <span className={styles.patternBullet}></span>
                    {pattern}
                  </div>
                ))
              ) : (
                <div className={styles.emptyPatterns}>No sleep patterns detected yet. Log more entries!</div>
              )}
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
