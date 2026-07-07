'use client';

import React, { useEffect, useState } from 'react';
import GlassCard from '@/components/ui/GlassCard';
import Badge from '@/components/ui/Badge';
import Skeleton from '@/components/ui/Skeleton';
import StatCard from '@/components/ui/StatCard';
import { fetchAnalysis, fetchReport } from '@/lib/api';
import { SleepAnalysis, WeeklyReportResponse } from '@/lib/types';
import styles from './page.module.css';

export default function ReportPage() {
  const userId = 'demo-user';
  const [analysis, setAnalysis] = useState<SleepAnalysis | null>(null);
  const [report, setReport] = useState<WeeklyReportResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [analysisData, reportData] = await Promise.all([
          fetchAnalysis(userId, 7),
          fetchReport(userId),
        ]);
        setAnalysis(analysisData);
        setReport(reportData);
      } catch (err) {
        console.error('Error fetching report data:', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const getVerdictLabel = (verdict: string) => {
    switch (verdict) {
      case 'EXCELLENT':
        return '🟢 Excellent';
      case 'ON_TRACK':
        return '🟢 On Track';
      case 'IMPROVING':
        return '🟡 Improving';
      case 'NEEDS_ATTENTION':
        return '🔴 Needs Attention';
      default:
        return 'ℹ️ Unknown';
    }
  };

  const getVerdictBadgeVariant = (verdict: string) => {
    switch (verdict) {
      case 'EXCELLENT':
        return 'excellent';
      case 'ON_TRACK':
        return 'good';
      case 'IMPROVING':
        return 'fair';
      case 'NEEDS_ATTENTION':
        return 'bad';
      default:
        return 'neutral';
    }
  };

  if (loading) {
    return (
      <div className={styles.loadingContainer}>
        <Skeleton width="240px" height="36px" />
        <Skeleton width="100%" height="200px" />
        <div className={styles.grid}>
          <Skeleton width="100%" height="280px" />
          <Skeleton width="100%" height="280px" />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Weekly Sleep Report</h1>
          <p className={styles.subtitle}>Insights generated from your sleep journals over the last 7 days.</p>
        </div>
        {analysis && (
          <Badge variant={getVerdictBadgeVariant(analysis.verdict)}>
            {getVerdictLabel(analysis.verdict)}
          </Badge>
        )}
      </header>

      {/* Overview Cards */}
      {analysis && (
        <div className={styles.statsRow}>
          <StatCard
            icon="⭐"
            label="Average Score"
            value={`${Math.round(analysis.average_score)}/100`}
            subValue="7-day sleep rating"
          />
          <StatCard
            icon="⏳"
            label="Average Duration"
            value={`${analysis.average_duration.toFixed(1)}h`}
            subValue="Target: 7.5–8.0h"
          />
          <StatCard
            icon="🔔"
            label="Average Interruptions"
            value={`${analysis.average_wake_ups.toFixed(1)}`}
            subValue="Wake-ups per night"
          />
          <StatCard
            icon="🔥"
            label="Consistency Streak"
            value={`${analysis.streak_days} days`}
            subValue="Check-ins recorded"
          />
        </div>
      )}

      {/* Message and Action Plan */}
      <div className={styles.grid}>
        {report && (
          <GlassCard className={styles.reportMessageCard}>
            <h3 className={styles.cardTitle}>🏋️ Concierge Summary</h3>
            <div className={styles.conciergeMessage}>
              {report.telegram_message.split('\n\n').map((para, i) => (
                <p key={i} className={styles.messagePara}>
                  {para.replace(/\*(.*?)\*/g, '$1')}
                </p>
              ))}
            </div>
          </GlassCard>
        )}

        {analysis && (
          <GlassCard className={styles.actionPlanCard}>
            <h3 className={styles.cardTitle}>🎯 Personalized Action Plan</h3>
            <div className={styles.recommendationsList}>
              {analysis.recommendations.map((rec, i) => (
                <div key={i} className={styles.recItem}>
                  <div className={styles.recBadge}>Priority {i + 1}</div>
                  <p className={styles.recText}>{rec}</p>
                </div>
              ))}
            </div>
          </GlassCard>
        )}
      </div>

      {/* Behavioral Correlations */}
      {analysis && (
        <div className={styles.grid}>
          <GlassCard className={styles.correlationCard}>
            <h3 className={styles.cardTitle}>☕ Caffeine Correlation</h3>
            <p className={styles.correlationText}>
              {analysis.caffeine_impact || 'Not enough data yet to establish a direct correlation with caffeine consumption timings.'}
            </p>
          </GlassCard>

          <GlassCard className={styles.correlationCard}>
            <h3 className={styles.cardTitle}>📱 Screen Time Correlation</h3>
            <p className={styles.correlationText}>
              {analysis.screen_time_impact || 'No screen time correlations detected this week. Try keeping screen use logged.'}
            </p>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
