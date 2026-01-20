'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { SidebarLayout } from '@/components/shared';
import { authApi } from '@/lib/api-v3';

export default function Home() {
  const router = useRouter();

  // Check authentication status
  const { data: authStatus, isLoading } = useQuery({
    queryKey: ['authStatus'],
    queryFn: authApi.getStatus,
    retry: false,
  });

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoading && authStatus && !authStatus.authenticated) {
      router.replace('/login');
    }
  }, [authStatus, isLoading, router]);

  // Show loading while checking auth
  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-xl animate-pulse">
            <span className="text-3xl">🔬</span>
          </div>
          <p className="text-slate-500 dark:text-slate-400">인증 확인 중...</p>
        </div>
      </div>
    );
  }

  // If not authenticated, show loading (will redirect)
  if (!authStatus?.authenticated) {
    return (
      <div className="h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-xl">
            <span className="text-3xl">🔬</span>
          </div>
          <p className="text-slate-500 dark:text-slate-400">로그인 페이지로 이동 중...</p>
        </div>
      </div>
    );
  }

  return (
    <SidebarLayout>
      <div className="h-full flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
        <div className="text-center max-w-lg px-6">
          {/* Logo */}
          <div className="relative mb-8 inline-block">
            <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-2xl shadow-primary-500/25">
              <span className="text-5xl">🔬</span>
            </div>
            <div className="absolute -bottom-2 -right-2 w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center shadow-lg">
              <span className="text-xl">✨</span>
            </div>
          </div>

          {/* Title */}
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-4">
            DeepResearcher에 오신 것을 환영합니다
          </h1>

          {/* Description */}
          <p className="text-slate-500 dark:text-slate-400 mb-8 leading-relaxed">
            왼쪽 사이드바에서 프로젝트를 선택하거나,
            새 연구를 시작해 AI와 함께하는 연구 여정을 시작하세요.
          </p>

          {/* Feature Cards */}
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="p-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
              <div className="text-2xl mb-2">💡</div>
              <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                연구 정의
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                아이디어를 구체화하세요
              </div>
            </div>
            <div className="p-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
              <div className="text-2xl mb-2">📚</div>
              <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                문헌 검토
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                논문 검색 및 관리
              </div>
            </div>
            <div className="p-4 bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
              <div className="text-2xl mb-2">📝</div>
              <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                논문 작성
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                AI와 함께 집필하세요
              </div>
            </div>
          </div>

          {/* Workflow Diagram */}
          <div className="p-4 bg-slate-100 dark:bg-slate-800/50 rounded-xl">
            <div className="text-xs font-medium text-slate-500 dark:text-slate-400 mb-3">
              병렬 프로세스 워크플로우
            </div>
            <div className="flex items-center justify-center gap-2 text-xs">
              <div className="px-3 py-1.5 bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 rounded-lg font-medium">
                연구 & 실험
              </div>
              <div className="flex flex-col items-center gap-1">
                <svg
                  className="w-4 h-4 text-slate-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 7l5 5m0 0l-5 5m5-5H6"
                  />
                </svg>
                <span className="text-[10px] text-slate-400">해금</span>
              </div>
              <div className="flex flex-col gap-1">
                <div className="px-3 py-1.5 bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 rounded-lg font-medium">
                  문헌 검토
                </div>
                <div className="px-3 py-1.5 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded-lg font-medium">
                  논문 작성
                </div>
              </div>
            </div>
          </div>

          {/* Version Info */}
          <div className="mt-8 text-xs text-slate-400 dark:text-slate-500">
            v3.0 - 병렬 프로세스 아키텍처
          </div>
        </div>
      </div>
    </SidebarLayout>
  );
}
