import {
  SleepEntry,
  UserProfile,
  SleepAnalysis,
  PlanAdjustment,
  HistoryResponse,
  WeeklyReportResponse,
} from './types';

// Fallback to localhost:8000 in dev
const API_BASE = process.env.NEXT_PUBLIC_AGENT_SERVER_URL || 'http://localhost:8000';

export async function fetchHistory(userId: string, days = 7): Promise<HistoryResponse> {
  const res = await fetch(`${API_BASE}/api/history/${userId}?days=${days}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Failed to fetch sleep history: ${res.statusText}`);
  return res.json();
}

export async function fetchProfile(userId: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/profile/${userId}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Failed to fetch profile: ${res.statusText}`);
  return res.json();
}

export async function fetchLatest(userId: string): Promise<SleepEntry | null> {
  try {
    const res = await fetch(`${API_BASE}/api/latest/${userId}`, {
      cache: 'no-store',
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch latest: ${res.statusText}`);
    return res.json();
  } catch (error) {
    console.error('Error fetching latest sleep log:', error);
    return null;
  }
}

export async function fetchAnalysis(userId: string, days = 7): Promise<SleepAnalysis> {
  const res = await fetch(`${API_BASE}/api/analysis/${userId}?days=${days}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Failed to fetch sleep analysis: ${res.statusText}`);
  return res.json();
}

export async function fetchPlan(userId: string): Promise<PlanAdjustment> {
  const res = await fetch(`${API_BASE}/api/plan/${userId}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Failed to fetch plan: ${res.statusText}`);
  return res.json();
}

export async function fetchReport(userId: string): Promise<WeeklyReportResponse> {
  const res = await fetch(`${API_BASE}/api/report/${userId}`, {
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Failed to fetch weekly report: ${res.statusText}`);
  return res.json();
}

export async function registerUser(
  userId: string,
  username: string,
  targetWakeTime = '07:00',
  ageYears?: number
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      username,
      target_wake_time: targetWakeTime,
      age_years: ageYears,
    }),
  });
  if (!res.ok) throw new Error(`Failed to register user: ${res.statusText}`);
  return res.json();
}

export async function submitCheckin(
  userId: string,
  rawText: string
): Promise<any> {
  const res = await fetch(`${API_BASE}/api/checkin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      raw_text: rawText,
    }),
  });
  if (!res.ok) throw new Error(`Failed to submit check-in: ${res.statusText}`);
  return res.json();
}
