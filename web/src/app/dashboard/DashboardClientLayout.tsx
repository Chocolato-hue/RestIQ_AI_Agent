'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { CopilotKit } from '@copilotkit/react-core';
import { CopilotSidebar } from '@copilotkit/react-ui';
import CopilotActionsRegister from '@/components/copilot/CopilotActionsRegister';
import styles from './layout.module.css';
import '@copilotkit/react-ui/styles.css';

export default function DashboardClientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  const navigation = [
    { name: 'Dashboard', href: '/dashboard', icon: '🌙' },
    { name: 'Weekly Report', href: '/dashboard/report', icon: '📈' },
    { name: 'Back to Home', href: '/', icon: '🏠' },
  ];

  return (
    <CopilotKit runtimeUrl="/api/copilotkit" agent="restiq">
      <CopilotActionsRegister />
      <CopilotSidebar
        defaultOpen={true}
        clickOutsideToClose={false}
        labels={{
          title: 'RestIQ Sleep Concierge',
          initial: 'Hi! I am RestIQ, your sleep concierge. Let me know how you slept or tell me to generate your weekly report 🌙',
          placeholder: 'How did you sleep last night...',
        }}
      >
        <div className={styles.layout}>
          {/* Dashboard Sidebar */}
          <aside className={styles.sidebar}>
            <div className={styles.sidebarBrand}>
              <span className={styles.brandLogo}>🌙</span>
              <span className={styles.brandText}>RestIQ</span>
            </div>
            
            <nav className={styles.nav}>
              {navigation.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={`${styles.navLink} ${isActive ? styles.active : ''}`}
                  >
                    <span className={styles.navIcon}>{item.icon}</span>
                    <span className={styles.navText}>{item.name}</span>
                  </Link>
                );
              })}
            </nav>
            
            <div className={styles.sidebarFooter}>
              <div className={styles.userBadge}>
                <div className={styles.avatar}>D</div>
                <div className={styles.userInfo}>
                  <div className={styles.userName}>Demo User</div>
                  <div className={styles.userRole}>Circadian Plan Active</div>
                </div>
              </div>
            </div>
          </aside>
          
          {/* Main Workspace */}
          <main className={styles.mainContent}>
            {children}
          </main>
        </div>
      </CopilotSidebar>
    </CopilotKit>
  );
}
