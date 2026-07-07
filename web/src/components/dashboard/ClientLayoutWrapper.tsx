'use client';

import dynamic from 'next/dynamic';
import React from 'react';

// Dynamic import with ssr: false inside a Client Component wrapper
const DashboardClientLayout = dynamic(
  () => import('../../app/dashboard/DashboardClientLayout'),
  { ssr: false }
);

export default function ClientLayoutWrapper({ children }: { children: React.ReactNode }) {
  return <DashboardClientLayout>{children}</DashboardClientLayout>;
}
