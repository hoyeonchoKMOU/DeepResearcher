'use client';

import { ReactNode, useState, useEffect } from 'react';
import { Sidebar } from '@/components/Sidebar';

interface SidebarLayoutProps {
  children: ReactNode;
  currentProjectId?: string;
  currentProcess?: 'research' | 'literature-org' | 'literature-search' | 'paper';
}

// LocalStorage key for sidebar state
const SIDEBAR_COLLAPSED_KEY = 'deepresearcher-sidebar-collapsed';

export function SidebarLayout({
  children,
  currentProjectId,
  currentProcess,
}: SidebarLayoutProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  // Load collapsed state from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (saved !== null) {
      setIsCollapsed(saved === 'true');
    }
    setIsHydrated(true);
  }, []);

  // Save collapsed state to localStorage
  const toggleSidebar = () => {
    const newState = !isCollapsed;
    setIsCollapsed(newState);
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(newState));
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900 overflow-hidden">
      {/* Sidebar */}
      <div
        className={`relative shrink-0 transition-all duration-300 ease-in-out ${
          isCollapsed ? 'w-0' : 'w-[280px]'
        }`}
      >
        <div
          className={`absolute inset-y-0 left-0 w-[280px] transition-transform duration-300 ease-in-out ${
            isCollapsed ? '-translate-x-full' : 'translate-x-0'
          }`}
        >
          <Sidebar
            currentProjectId={currentProjectId}
            currentProcess={currentProcess}
          />
        </div>
      </div>

      {/* Toggle Button */}
      <button
        onClick={toggleSidebar}
        className={`absolute z-50 flex items-center justify-center w-6 h-12 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-r-lg transition-all duration-300 ease-in-out ${
          isCollapsed ? 'left-0' : 'left-[280px]'
        } top-1/2 -translate-y-1/2 shadow-lg`}
        title={isCollapsed ? 'Show sidebar' : 'Hide sidebar'}
      >
        <svg
          className={`w-4 h-4 text-slate-300 transition-transform duration-300 ${
            isCollapsed ? 'rotate-0' : 'rotate-180'
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
      </button>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
