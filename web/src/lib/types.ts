export type SleepQuality = 'POOR' | 'FAIR' | 'GOOD' | 'EXCELLENT';
export type MoodOnWake = 'TERRIBLE' | 'TIRED' | 'OKAY' | 'GOOD' | 'GREAT';
export type VerdictLabel = 'NEEDS_ATTENTION' | 'IMPROVING' | 'ON_TRACK' | 'EXCELLENT';
export type PlanStatus = 'IMPROVING' | 'DECLINING' | 'STABLE' | 'INSUFFICIENT_DATA';
export type PlanTrigger = 'ROLLING_TREND' | 'WEEKLY_COMPARISON' | 'STREAK_OVERRIDE' | 'NONE';

export interface SleepEntry {
  user_id: string;
  date: string; // YYYY-MM-DD
  bedtime: string; // HH:MM
  wake_time: string; // HH:MM
  sleep_duration: number;
  wake_up_count: number;
  sleep_quality: SleepQuality;
  mood_on_wake: MoodOnWake;
  caffeine_after_2pm: boolean;
  exercise_today: boolean;
  screen_time_before_bed: boolean;
  focus_level: number; // 1-5
  energy_level: number; // 1-5
  notes: string;
  score: number; // 0-100
}

export interface UserProfile {
  user_id: string;
  username: string;
  target_wake_time: string;
  created_at: string;
  telegram_chat_id?: string;
  age_years?: number;
}

export interface CircadianResult {
  recommended_bedtime: string;
  wind_down_time: string;
  melatonin_onset: string;
}

export interface PlanAdjustment {
  adjusted: boolean;
  status: PlanStatus;
  reason: string;
  new_target_bedtime?: string;
  rolling_avg_score?: number;
  previous_week_avg_score?: number;
  triggered_by: PlanTrigger;
}

export interface SleepAnalysis {
  average_score: number;
  average_duration: number;
  average_wake_ups: number;
  streak_days: number;
  best_night?: SleepEntry;
  worst_night?: SleepEntry;
  verdict: VerdictLabel;
  patterns_detected: string[];
  recommendations: string[];
  caffeine_impact?: string;
  screen_time_impact?: string;
}

export interface HistoryResponse {
  user_id: string;
  days: number;
  count: number;
  entries: SleepEntry[];
}

export interface WeeklyReportResponse {
  telegram_message: string;
  plan_adjustment: PlanAdjustment;
  chart_path: string;
}
