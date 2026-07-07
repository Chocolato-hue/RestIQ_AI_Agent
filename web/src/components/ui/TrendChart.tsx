'use client';

import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import styles from './TrendChart.module.css';

interface TrendChartProps {
  data: Array<{ day: string; score: number }>;
  height?: number;
}

export default function TrendChart({ data, height = 240 }: TrendChartProps) {
  // Safe default formatting for Tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className={styles.tooltip}>
          <p className={styles.tooltipLabel}>{payload[0].payload.day}</p>
          <p className={styles.tooltipValue}>
            Score: <span className={styles.scoreText}>{payload[0].value}/100</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className={styles.container} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 10, right: 10, left: -25, bottom: 0 }}
        >
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--color-primary)" stopOpacity={0.3} />
              <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            vertical={false}
            stroke="rgba(148, 163, 184, 0.05)"
          />
          <XAxis
            dataKey="day"
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11, fontWeight: 500 }}
            dy={8}
          />
          <YAxis
            domain={[0, 100]}
            tickLine={false}
            axisLine={false}
            tickCount={6}
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11, fontWeight: 500 }}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(99, 102, 241, 0.15)', strokeWidth: 1.5 }} />
          <Area
            type="monotone"
            dataKey="score"
            stroke="var(--color-primary)"
            strokeWidth={3}
            fillOpacity={1}
            fill="url(#chartGradient)"
            activeDot={{
              r: 6,
              fill: 'var(--color-primary)',
              stroke: 'var(--color-bg)',
              strokeWidth: 2,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
