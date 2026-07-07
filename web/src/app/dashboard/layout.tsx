import React from 'react';
import ClientLayoutWrapper from '@/components/dashboard/ClientLayoutWrapper';

export const metadata = {
  title: 'Dashboard — RestIQ',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ClientLayoutWrapper>{children}</ClientLayoutWrapper>;
}
