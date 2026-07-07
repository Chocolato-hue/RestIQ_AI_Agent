'use client';

import React from 'react';
import { useCopilotAction } from '@copilotkit/react-core';
import { useRouter } from 'next/navigation';
import SleepScoreCard from './SleepScoreCard';
import BedtimeRecommendation from './BedtimeRecommendation';
import CoachingTip from './CoachingTip';
import WeeklyInsightCard from './WeeklyInsightCard';
import QuickCheckinForm from './QuickCheckinForm';

export default function CopilotActionsRegister() {
  const router = useRouter();

  // 1. Navigation Action (allows the agent to redirect the user)
  useCopilotAction({
    name: 'navigateTo',
    description: 'Navigate to different dashboard pages.',
    parameters: [
      {
        name: 'page',
        type: 'string',
        description: 'The target page to navigate to: dashboard, report, home',
        required: true,
      },
    ],
    handler: async ({ page }) => {
      if (page === 'dashboard') {
        router.push('/dashboard');
      } else if (page === 'report') {
        router.push('/dashboard/report');
      } else if (page === 'home') {
        router.push('/');
      }
    },
  });

  // 2. Sleep Score Card (Generative UI)
  useCopilotAction({
    name: 'renderSleepScoreCard',
    description: 'Render the sleep score result card directly in the chat window.',
    parameters: [
      { name: 'score', type: 'number', required: true },
      { name: 'duration', type: 'number', required: true },
      { name: 'bedtime', type: 'string', required: true },
      { name: 'wakeTime', type: 'string', required: true },
      { name: 'quality', type: 'string', required: true },
      { name: 'coachRemarks', type: 'string', required: false },
    ],
    render: ({ args }) => {
      return (
        <SleepScoreCard
          score={args.score ?? 0}
          duration={args.duration ?? 0}
          bedtime={args.bedtime ?? ''}
          wakeTime={args.wakeTime ?? ''}
          quality={args.quality ?? ''}
          coachRemarks={args.coachRemarks}
        />
      );
    },
  });

  // 3. Bedtime Recommendation (Generative UI)
  useCopilotAction({
    name: 'renderBedtimeRecommendation',
    description: 'Render tonight\'s recommended bedtime schedule in the chat window.',
    parameters: [
      { name: 'bedtime', type: 'string', required: true },
      { name: 'windDownTime', type: 'string', required: false },
      { name: 'sleepDuration', type: 'number', required: false },
    ],
    render: ({ args }) => {
      return (
        <BedtimeRecommendation
          bedtime={args.bedtime ?? ''}
          windDownTime={args.windDownTime}
          sleepDuration={args.sleepDuration}
        />
      );
    },
  });

  // 4. Coaching Tip (Generative UI)
  useCopilotAction({
    name: 'renderCoachingTip',
    description: 'Render a personalized sleep coaching tip in the chat window.',
    parameters: [
      { name: 'tip', type: 'string', required: true },
      {
        name: 'category',
        type: 'string',
        description: 'Category of advice: caffeine, screen, exercise, duration, general',
        required: false,
      },
    ],
    render: ({ args }) => {
      const cat = (args.category || 'general') as 'caffeine' | 'screen' | 'exercise' | 'duration' | 'general';
      return <CoachingTip tip={args.tip ?? ''} category={cat} />;
    },
  });

  // 5. Weekly Insight Card (Generative UI)
  useCopilotAction({
    name: 'renderWeeklyInsightCard',
    description: 'Render the 7-day sleep report overview/summary card in the chat window.',
    parameters: [
      { name: 'avgScore', type: 'number', required: true },
      { name: 'avgDuration', type: 'number', required: true },
      { name: 'streak', type: 'number', required: true },
      { name: 'verdict', type: 'string', required: true },
    ],
    render: ({ args }) => {
      return (
        <WeeklyInsightCard
          avgScore={args.avgScore ?? 0}
          avgDuration={args.avgDuration ?? 0}
          streak={args.streak ?? 0}
          verdict={args.verdict ?? ''}
        />
      );
    },
  });

  // 6. Inline Quick Checkin Form (Generative UI)
  useCopilotAction({
    name: 'renderQuickCheckinForm',
    description: 'Render a quick sleep check-in form in the chat window so the user can fill it manually.',
    parameters: [],
    render: () => {
      const handleFormSubmit = async (data: any) => {
        // Can make an API call to save check-in or send to ADK agent
        console.log('Submitted sleep check-in:', data);
      };
      return <QuickCheckinForm onSubmit={handleFormSubmit} />;
    },
  });

  return null;
}
