'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ProjectTree } from './ProjectTree';
import { projectApi, authApi, ProjectV3, AuthStatus } from '@/lib/api-v3';

interface SidebarProps {
  currentProjectId?: string;
  currentProcess?: 'research' | 'literature-org' | 'literature-search' | 'paper';
}

export function Sidebar({ currentProjectId, currentProcess }: SidebarProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [newTopic, setNewTopic] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Fetch projects
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects-v3'],
    queryFn: projectApi.getProjects,
    refetchInterval: 5000,
  });

  // Fetch auth status
  const { data: authStatus, isLoading: isAuthLoading } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.getStatus,
    refetchInterval: 30000, // Refresh every 30 seconds
    retry: 1,
  });

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: async () => {
      const { auth_url } = await authApi.getLoginUrl();
      window.location.href = auth_url;
    },
  });

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-status'] });
      // Redirect to login page after logout
      router.push('/login');
    },
  });

  // Create project mutation
  const createProject = useMutation({
    mutationFn: projectApi.createProject,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['projects-v3'] });
      setNewTopic('');
      setIsCreating(false);
      router.push(`/project/${data.project_id}/research`);
    },
  });

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (newTopic.trim()) {
      createProject.mutate(newTopic.trim());
    }
  };

  const handleLogin = () => {
    loginMutation.mutate();
  };

  const handleLogout = () => {
    logoutMutation.mutate();
  };

  return (
    <aside className="w-[280px] h-full bg-slate-900 text-white flex flex-col border-r border-slate-800">
      {/* Logo Header - Clickable link to main page */}
      <Link
        href="/"
        className="block shrink-0 px-4 py-4 border-b border-slate-800 hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-lg">
            <span className="text-lg">🔬</span>
          </div>
          <div>
            <h1 className="font-bold text-white text-sm">DeepResearcher</h1>
            <p className="text-[10px] text-slate-400">AI 연구 도우미</p>
          </div>
        </div>
      </Link>

      {/* New Research Button */}
      <div className="shrink-0 p-3">
        {isCreating ? (
          <form onSubmit={handleCreateProject} className="space-y-2">
            <input
              type="text"
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              placeholder="연구 주제를 입력하세요..."
              autoFocus
              className="w-full px-3 py-2 text-sm bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!newTopic.trim() || createProject.isPending}
                className="flex-1 px-3 py-1.5 text-xs font-medium bg-primary-600 hover:bg-primary-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {createProject.isPending ? '생성 중...' : '생성'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsCreating(false);
                  setNewTopic('');
                }}
                className="px-3 py-1.5 text-xs font-medium bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
              >
                취소
              </button>
            </div>
          </form>
        ) : (
          <button
            onClick={() => setIsCreating(true)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 rounded-xl text-sm font-medium transition-all duration-200"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            새 연구 시작
          </button>
        )}
      </div>

      {/* Projects List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading ? (
          <div className="space-y-2 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 bg-slate-800 rounded-lg"
              />
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-8 px-4">
            <div className="text-3xl mb-3">📚</div>
            <p className="text-sm text-slate-400">프로젝트가 없습니다</p>
            <p className="text-xs text-slate-500 mt-1">
              위에서 첫 번째 연구 프로젝트를 만들어보세요
            </p>
          </div>
        ) : (
          <ProjectTree
            projects={projects}
            currentProjectId={currentProjectId}
            currentProcess={currentProcess}
          />
        )}
      </div>

      {/* Auth Status & Footer */}
      <div className="shrink-0 border-t border-slate-800">
        {/* Auth Status */}
        <div className="p-3 space-y-2">
          {isAuthLoading ? (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <div className="w-2 h-2 rounded-full bg-slate-600 animate-pulse" />
              <span>인증 확인 중...</span>
            </div>
          ) : authStatus?.authenticated ? (
            <div className="space-y-2">
              {/* User Info */}
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-green-600/20 flex items-center justify-center">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-slate-300 truncate">
                    {authStatus.email || '인증됨'}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    모델: {authStatus.model}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  disabled={logoutMutation.isPending}
                  className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
                  title="Logout"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={handleLogin}
              disabled={loginMutation.isPending}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
              </svg>
              {loginMutation.isPending ? '이동 중...' : 'Google로 로그인'}
            </button>
          )}
        </div>

        {/* Version Footer */}
        <div className="px-3 pb-3">
          <div className="text-[10px] text-slate-500 text-center">
            v3.0 - Parallel Process Architecture
          </div>
        </div>
      </div>
    </aside>
  );
}
