'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { KoreanMarkdown } from '@/components/KoreanMarkdown';
import { SidebarLayout, PhaseIndicator, ModelSelector, getSelectedModel } from '@/components/shared';
import {
  projectApi,
  researchExperimentApi,
  documentApi,
  authApi,
  ResearchExperimentResponse,
  ProjectStatusV3,
  Message,
  DocumentType,
  ResetRequest,
} from '@/lib/api-v3';

// ============================================================================
// Constants
// ============================================================================
const MIN_PANEL_WIDTH = 320;
const DEFAULT_SPLIT_RATIO = 0.45;
const STORAGE_KEY = 'deepresearcher-split-ratio';

// Agent Display Configuration
const AGENT_CONFIG: Record<
  string,
  { color: string; bgLight: string; bgDark: string; icon: string }
> = {
  research_discussion: {
    color: 'purple',
    bgLight: 'bg-purple-50',
    bgDark: 'dark:bg-purple-950/30',
    icon: '🎓',
  },
  experiment_design: {
    color: 'orange',
    bgLight: 'bg-orange-50',
    bgDark: 'dark:bg-orange-950/30',
    icon: '🔬',
  },
  system: {
    color: 'slate',
    bgLight: 'bg-slate-50',
    bgDark: 'dark:bg-slate-800/50',
    icon: '⚙️',
  },
  user: {
    color: 'primary',
    bgLight: 'bg-primary-600',
    bgDark: 'bg-primary-600',
    icon: '👤',
  },
};

const AGENT_DISPLAY_NAMES: Record<string, string> = {
  research_discussion: '연구 어드바이저',
  experiment_design: '실험 설계 도우미',
  system: '시스템',
  user: '나',
};

// ============================================================================
// Hooks
// ============================================================================
function useResizableSplit(isEnabled: boolean) {
  const [splitRatio, setSplitRatio] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? parseFloat(saved) : DEFAULT_SPLIT_RATIO;
    }
    return DEFAULT_SPLIT_RATIO;
  });
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging || !isEnabled) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const containerWidth = containerRect.width;
      const mouseX = e.clientX - containerRect.left;
      let newRatio = 1 - mouseX / containerWidth;
      const minRatio = MIN_PANEL_WIDTH / containerWidth;
      const maxRatio = 1 - MIN_PANEL_WIDTH / containerWidth;
      newRatio = Math.max(minRatio, Math.min(maxRatio, newRatio));
      setSplitRatio(newRatio);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      localStorage.setItem(STORAGE_KEY, splitRatio.toString());
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isDragging, isEnabled, splitRatio]);

  return { splitRatio, isDragging, containerRef, handleMouseDown };
}

// ============================================================================
// Components
// ============================================================================
function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-start gap-3 max-w-[85%]">
        <div className="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
          <span className="text-sm">🎓</span>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-2xl rounded-tl-md px-5 py-4 shadow-sm border border-slate-200/50 dark:border-slate-700/50">
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              <span
                className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
                style={{ animationDelay: '0ms' }}
              />
              <span
                className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
                style={{ animationDelay: '150ms' }}
              />
              <span
                className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"
                style={{ animationDelay: '300ms' }}
              />
            </div>
            <span className="text-sm text-slate-400 dark:text-slate-500 ml-2">
              생각하는 중...
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  formatTimestamp,
}: {
  message: Message;
  formatTimestamp: (ts: string) => string;
}) {
  const isUser = message.agent === 'user';
  const isSystem = message.agent === 'system';
  const config = AGENT_CONFIG[message.agent] || AGENT_CONFIG.system;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] group">
          <div className="bg-gradient-to-br from-primary-600 to-primary-700 text-white rounded-2xl rounded-tr-md px-5 py-3 shadow-lg shadow-primary-500/20">
            <div className="whitespace-pre-wrap text-[15px] leading-relaxed">
              {message.content}
            </div>
          </div>
          <div className="text-[11px] text-slate-400 dark:text-slate-500 mt-1.5 text-right opacity-0 group-hover:opacity-100 transition-opacity">
            {formatTimestamp(message.timestamp)}
          </div>
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-full text-sm text-slate-600 dark:text-slate-400">
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
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="italic">{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="flex items-start gap-3 max-w-[85%] group">
        <div
          className={`shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-${config.color}-500 to-${config.color}-600 flex items-center justify-center shadow-lg shadow-${config.color}-500/20`}
        >
          <span className="text-sm">{config.icon}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              {AGENT_DISPLAY_NAMES[message.agent] || message.agent}
            </span>
            <span className="text-[11px] text-slate-400 dark:text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity">
              {formatTimestamp(message.timestamp)}
            </span>
          </div>
          <div
            className={`${config.bgLight} ${config.bgDark} rounded-2xl rounded-tl-md px-5 py-4 border border-slate-200/50 dark:border-slate-700/50`}
          >
            <div className="prose prose-slate dark:prose-invert prose-sm max-w-none">
              <KoreanMarkdown>{message.content}</KoreanMarkdown>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  onStart,
  isPending,
  isAuthenticated,
}: {
  onStart: () => void;
  isPending: boolean;
  isAuthenticated: boolean;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 py-12">
      <div className="relative mb-8">
        <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-primary-500 to-purple-600 flex items-center justify-center shadow-2xl shadow-primary-500/25">
          <span className="text-5xl">💡</span>
        </div>
      </div>

      <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">
        연구 여정을 시작할 준비가 되었습니다
      </h2>
      <p className="text-slate-500 dark:text-slate-400 mb-8 max-w-lg leading-relaxed">
        AI 연구 어드바이저와 대화를 시작하세요. 함께 아이디어를 다듬고,
        연구의 신규성을 평가하며, 탄탄한 연구 기반을 만들어 갑니다.
      </p>

      {!isAuthenticated && (
        <div className="flex items-center gap-2 px-4 py-3 mb-6 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl max-w-md">
          <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-sm text-amber-700 dark:text-amber-300">
            시작하려면 먼저 로그인이 필요합니다. 사이드바에서 Google로 로그인해주세요.
          </span>
        </div>
      )}

      <button
        onClick={onStart}
        disabled={isPending || !isAuthenticated}
        className="group relative px-8 py-4 bg-gradient-to-r from-primary-600 to-purple-600 text-white rounded-2xl font-semibold shadow-xl shadow-primary-500/25 hover:shadow-2xl hover:shadow-primary-500/30 transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span className="relative z-10 flex items-center gap-3">
          {isPending ? (
            <>
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              시작하는 중...
            </>
          ) : (
            <>
              대화 시작하기
              <svg
                className="w-5 h-5 group-hover:translate-x-1 transition-transform"
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
            </>
          )}
        </span>
      </button>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================
// Artifact Update Notification Component
function ArtifactUpdateNotification({ phase }: { phase: string }) {
  return (
    <div className="flex justify-center my-4 animate-fade-in">
      <div className="inline-flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-purple-50 to-primary-50 dark:from-purple-950/40 dark:to-primary-950/40 rounded-full text-sm border border-purple-200/50 dark:border-purple-800/50 shadow-sm">
        <div className="w-5 h-5 rounded-full bg-purple-100 dark:bg-purple-900/50 flex items-center justify-center">
          <svg
            className="w-3 h-3 text-purple-600 dark:text-purple-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </div>
        <span className="text-purple-700 dark:text-purple-300 font-medium">
          {phase === 'research_definition' ? '연구 정의' : '실험 설계'} 업데이트됨
        </span>
        <span className="text-purple-500 dark:text-purple-400 text-xs">
          {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  );
}

export default function ResearchPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const queryClient = useQueryClient();

  const [inputMessage, setInputMessage] = useState('');
  const [isWaitingForResponse, setIsWaitingForResponse] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [showArtifact, setShowArtifact] = useState(true);
  const [artifactUpdates, setArtifactUpdates] = useState<{ id: number; phase: string }[]>([]);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetType, setResetType] = useState<'all' | 'messages' | 'artifact'>('all');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageCountWhenSentRef = useRef<number>(-1);
  const previousArtifactRef = useRef<string | null>(null);
  const updateIdRef = useRef<number>(0);

  const { splitRatio, isDragging, containerRef, handleMouseDown } =
    useResizableSplit(showArtifact);

  // Fetch project status
  const {
    data: projectStatus,
    isLoading: loadingStatus,
    error: statusError,
  } = useQuery({
    queryKey: ['project-status', projectId],
    queryFn: () => projectApi.getStatus(projectId),
    refetchInterval: 5000,
  });

  // Fetch process state
  const {
    data: processState,
    isLoading: loadingProcess,
    error: processError,
  } = useQuery({
    queryKey: ['research-experiment', projectId],
    queryFn: () => researchExperimentApi.getState(projectId),
    refetchInterval: isWaitingForResponse ? 1000 : 3000,
  });

  // Fetch auth status for model info
  const { data: authStatus } = useQuery({
    queryKey: ['auth-status'],
    queryFn: authApi.getStatus,
    staleTime: 60000, // 1 minute
  });

  const messages = processState?.messages || [];
  const artifact = processState?.artifact || '';
  const currentPhase = processState?.current_phase || 'research_definition';

  // Start mutation
  const startProcess = useMutation({
    mutationFn: () => researchExperimentApi.start(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-experiment', projectId] });
    },
  });

  // Chat mutation - passes selected model from localStorage
  const sendMessage = useMutation({
    mutationFn: (content: string) => {
      const model = getSelectedModel();
      return researchExperimentApi.chat(projectId, content, model);
    },
  });

  // Switch phase mutation
  const switchPhase = useMutation({
    mutationFn: (phase: 'research_definition' | 'experiment_design') =>
      researchExperimentApi.switchPhase(projectId, phase),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-experiment', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project-status', projectId] });
    },
  });

  // Complete phase mutation
  const completePhase = useMutation({
    mutationFn: () => researchExperimentApi.complete(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-experiment', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project-status', projectId] });
      queryClient.invalidateQueries({ queryKey: ['projects-v3'] });
    },
  });

  // Reset mutation
  const resetProcess = useMutation({
    mutationFn: (options: ResetRequest) => researchExperimentApi.reset(projectId, options),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-experiment', projectId] });
      setShowResetConfirm(false);
      setArtifactUpdates([]);
      previousArtifactRef.current = null;
    },
  });

  const handleReset = (type: 'all' | 'messages' | 'artifact') => {
    const options: ResetRequest = {
      reset_messages: type === 'all' || type === 'messages',
      reset_artifact: type === 'all' || type === 'artifact',
    };
    resetProcess.mutate(options);
  };

  // Handle response detection
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (
        pendingMessage &&
        lastMsg.agent === 'user' &&
        lastMsg.content === pendingMessage
      ) {
        setPendingMessage(null);
      }
      if (
        isWaitingForResponse &&
        lastMsg.agent !== 'user' &&
        messages.length > messageCountWhenSentRef.current
      ) {
        setIsWaitingForResponse(false);
        setPendingMessage(null);
        messageCountWhenSentRef.current = -1;
      }
    }
  }, [messages, isWaitingForResponse, pendingMessage]);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, pendingMessage, isWaitingForResponse, artifactUpdates]);

  // Timeout for waiting
  useEffect(() => {
    if (isWaitingForResponse) {
      const timeout = setTimeout(() => setIsWaitingForResponse(false), 60000);
      return () => clearTimeout(timeout);
    }
  }, [isWaitingForResponse]);

  // Detect artifact updates and add notifications
  useEffect(() => {
    // Skip initial load (when previousArtifactRef is null)
    if (previousArtifactRef.current === null) {
      previousArtifactRef.current = artifact;
      return;
    }

    // Check if artifact actually changed (and is not empty)
    if (artifact && artifact !== previousArtifactRef.current) {
      updateIdRef.current += 1;
      setArtifactUpdates((prev) => [...prev, { id: updateIdRef.current, phase: currentPhase }]);
      previousArtifactRef.current = artifact;
    }
  }, [artifact, currentPhase]);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || isWaitingForResponse) return;

    const messageToSend = inputMessage.trim();
    messageCountWhenSentRef.current = messages.length;
    setPendingMessage(messageToSend);
    setIsWaitingForResponse(true);
    setInputMessage('');

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    sendMessage.mutate(messageToSend, {
      onSuccess: () =>
        queryClient.invalidateQueries({
          queryKey: ['research-experiment', projectId],
        }),
      onError: () => {
        setIsWaitingForResponse(false);
        setPendingMessage(null);
        messageCountWhenSentRef.current = -1;
      },
    });
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '';
    }
  };

  // Loading state
  if (loadingStatus || loadingProcess) {
    return (
      <SidebarLayout currentProjectId={projectId} currentProcess="research">
        <div className="h-full flex items-center justify-center">
          <div className="flex items-center gap-3 text-slate-500">
            <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span>불러오는 중...</span>
          </div>
        </div>
      </SidebarLayout>
    );
  }

  // Error state
  if (statusError || processError || !projectStatus) {
    return (
      <SidebarLayout currentProjectId={projectId} currentProcess="research">
        <div className="h-full flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-red-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">
              프로젝트를 찾을 수 없습니다
            </h2>
            <p className="text-slate-500 dark:text-slate-400 mb-6">
              찾으시는 프로젝트가 존재하지 않거나 삭제되었을 수 있습니다.
            </p>
            <button
              onClick={() => router.push('/')}
              className="px-6 py-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-xl font-medium hover:bg-slate-800 dark:hover:bg-slate-100 transition-colors"
            >
              홈으로 돌아가기
            </button>
          </div>
        </div>
      </SidebarLayout>
    );
  }

  const hasStarted = messages.length > 0;

  return (
    <SidebarLayout currentProjectId={projectId} currentProcess="research">
      <div className="h-full flex flex-col bg-gradient-to-br from-slate-50 via-slate-50 to-slate-100 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800">
        {/* Header */}
        <header className="shrink-0 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-b border-slate-200/50 dark:border-slate-700/50 px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white truncate">
                {projectStatus.topic}
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                연구 & 실험
              </p>
            </div>
            <button
              onClick={() => setShowArtifact(!showArtifact)}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                showArtifact
                  ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 ring-1 ring-purple-200 dark:ring-purple-800'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
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
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <span className="hidden sm:inline">산출물</span>
            </button>
          </div>
        </header>

        {/* Phase Indicator */}
        <div className="shrink-0 px-4 sm:px-6 py-3 border-b border-slate-200/50 dark:border-slate-700/50">
          <PhaseIndicator
            currentPhase={currentPhase}
            researchDefinitionComplete={projectStatus.research_definition_complete}
            experimentDesignComplete={projectStatus.experiment_design_complete}
            onSwitchPhase={(phase) => switchPhase.mutate(phase)}
            onComplete={() => completePhase.mutate()}
            isCompleting={completePhase.isPending}
          />
        </div>

        {/* Main Content */}
        <div ref={containerRef} className="flex-1 flex overflow-hidden px-4 py-4 gap-4">
          {/* Chat Panel */}
          <div
            className="flex flex-col min-w-0"
            style={{
              width: showArtifact ? `${(1 - splitRatio) * 100}%` : '100%',
              minWidth: showArtifact ? MIN_PANEL_WIDTH : undefined,
            }}
          >
            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-1 space-y-4 pb-4 scroll-smooth">
              {!hasStarted ? (
                <EmptyState
                  onStart={() => startProcess.mutate()}
                  isPending={startProcess.isPending}
                  isAuthenticated={authStatus?.authenticated ?? false}
                />
              ) : (
                <>
                  {messages.map((message, index) => {
                    // Check if there's an artifact update that should be shown after this message
                    // We show the update notification after AI responses (non-user messages)
                    const isLastMessage = index === messages.length - 1;
                    const isAIResponse = message.agent !== 'user';

                    return (
                      <div key={`${index}-${message.timestamp}`}>
                        <MessageBubble
                          message={message}
                          formatTimestamp={formatTimestamp}
                        />
                        {/* Show artifact update notification after the last AI response */}
                        {isLastMessage && isAIResponse && artifactUpdates.length > 0 && (
                          <ArtifactUpdateNotification
                            phase={artifactUpdates[artifactUpdates.length - 1].phase}
                          />
                        )}
                      </div>
                    );
                  })}

                  {pendingMessage && (
                    <div className="flex justify-end">
                      <div className="max-w-[75%]">
                        <div className="bg-gradient-to-br from-primary-600 to-primary-700 text-white rounded-2xl rounded-tr-md px-5 py-3 shadow-lg shadow-primary-500/20 opacity-70">
                          <div className="whitespace-pre-wrap text-[15px] leading-relaxed">
                            {pendingMessage}
                          </div>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-1.5 text-right flex items-center justify-end gap-1">
                          <svg
                            className="w-3 h-3 animate-spin"
                            fill="none"
                            viewBox="0 0 24 24"
                          >
                            <circle
                              className="opacity-25"
                              cx="12"
                              cy="12"
                              r="10"
                              stroke="currentColor"
                              strokeWidth="4"
                            />
                            <path
                              className="opacity-75"
                              fill="currentColor"
                              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                            />
                          </svg>
                          전송 중...
                        </div>
                      </div>
                    </div>
                  )}

                  {isWaitingForResponse && <TypingIndicator />}
                </>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            {hasStarted && (
              <div className="shrink-0">
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/50 dark:border-slate-700/50 p-3">
                  {/* Not authenticated warning */}
                  {authStatus && !authStatus.authenticated && (
                    <div className="flex items-center gap-2 px-4 py-3 mb-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl">
                      <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <span className="text-sm text-amber-700 dark:text-amber-300">
                        채팅을 사용하려면 로그인이 필요합니다. 사이드바에서 Google로 로그인해주세요.
                      </span>
                    </div>
                  )}
                  <form
                    onSubmit={handleSendMessage}
                    className="flex gap-3 items-end"
                  >
                    <div className="flex-1 relative">
                      <textarea
                        ref={textareaRef}
                        value={inputMessage}
                        onChange={(e) => setInputMessage(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
                            e.preventDefault();
                            if (inputMessage.trim() && !isWaitingForResponse && authStatus?.authenticated) {
                              handleSendMessage(e);
                            }
                          }
                        }}
                        disabled={isWaitingForResponse || !authStatus?.authenticated}
                        placeholder={
                          !authStatus?.authenticated
                            ? '로그인 후 채팅을 시작할 수 있습니다'
                            : isWaitingForResponse
                            ? '응답을 기다리는 중...'
                            : currentPhase === 'research_definition'
                            ? '연구 주제를 설명하거나 질문을 입력하세요...'
                            : '실험 설계에 대해 이야기해 보세요...'
                        }
                        rows={1}
                        className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border-0 rounded-xl text-[15px] text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:ring-2 focus:ring-primary-500/50 disabled:opacity-50 disabled:cursor-not-allowed resize-none min-h-[48px] max-h-[200px] overflow-y-auto transition-all"
                        style={{ height: 'auto' }}
                        onInput={(e) => {
                          const target = e.target as HTMLTextAreaElement;
                          target.style.height = 'auto';
                          target.style.height =
                            Math.min(target.scrollHeight, 200) + 'px';
                        }}
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={
                        !inputMessage.trim() ||
                        sendMessage.isPending ||
                        isWaitingForResponse ||
                        !authStatus?.authenticated
                      }
                      className="shrink-0 p-3 bg-primary-600 hover:bg-primary-700 text-white rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-primary-500/25 hover:shadow-xl hover:shadow-primary-500/30 disabled:shadow-none"
                    >
                      {isWaitingForResponse ? (
                        <svg
                          className="w-5 h-5 animate-spin"
                          fill="none"
                          viewBox="0 0 24 24"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-5 h-5"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                          />
                        </svg>
                      )}
                    </button>
                  </form>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500 mt-2 px-1">
                    <span>Enter로 전송, Shift+Enter로 줄바꿈</span>
                    {authStatus?.authenticated && (
                      <ModelSelector />
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Resizable Divider */}
          {showArtifact && (
            <div
              className={`shrink-0 w-3 cursor-col-resize relative group flex items-center justify-center rounded-full my-4 transition-colors duration-200 ${
                isDragging
                  ? 'bg-primary-200 dark:bg-primary-800'
                  : 'hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
              onMouseDown={handleMouseDown}
            >
              <div
                className={`w-1 h-12 rounded-full transition-all duration-200 ${
                  isDragging
                    ? 'bg-primary-500 h-20'
                    : 'bg-slate-300 dark:bg-slate-600 group-hover:bg-primary-400 group-hover:h-16'
                }`}
              />
            </div>
          )}

          {/* Artifact Panel */}
          {showArtifact && (
            <div
              className="flex flex-col bg-white dark:bg-slate-800 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/50 dark:border-slate-700/50 overflow-hidden"
              style={{
                width: `${splitRatio * 100}%`,
                minWidth: MIN_PANEL_WIDTH,
              }}
            >
              {/* Artifact Header */}
              <div className="shrink-0 px-5 py-4 border-b border-slate-200/50 dark:border-slate-700/50 bg-gradient-to-r from-purple-50 to-slate-50 dark:from-purple-950/30 dark:to-slate-900/50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center shadow-lg shadow-purple-500/20">
                      <svg
                        className="w-4 h-4 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                        {currentPhase === 'research_definition'
                          ? '연구 정의'
                          : '실험 설계'}
                      </h3>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        실시간 문서
                      </p>
                    </div>
                  </div>
                  {/* Action Buttons */}
                  <div className="flex items-center gap-2">
                    {/* Reset Button */}
                    <button
                      onClick={() => setShowResetConfirm(true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-800/50 rounded-lg transition-colors"
                      title="초기화"
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
                          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        />
                      </svg>
                      <span>초기화</span>
                    </button>
                    {/* Download Button */}
                    {artifact && (
                      <button
                        onClick={() =>
                          documentApi
                            .downloadDocument(projectId, currentPhase as DocumentType)
                            .catch((err) => console.error('Download failed:', err))
                        }
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-700 dark:text-purple-300 bg-purple-100 dark:bg-purple-900/40 hover:bg-purple-200 dark:hover:bg-purple-800/50 rounded-lg transition-colors"
                        title="Download as Markdown file"
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
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                          />
                        </svg>
                        <span>다운로드</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Artifact Content */}
              <div className="flex-1 overflow-y-auto p-6">
                {artifact ? (
                  <div className="prose prose-slate dark:prose-invert prose-sm max-w-none">
                    <KoreanMarkdown>{artifact}</KoreanMarkdown>
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full text-center py-12">
                    <div className="w-16 h-16 rounded-2xl bg-slate-100 dark:bg-slate-700 flex items-center justify-center mb-4">
                      <svg
                        className="w-8 h-8 text-slate-400"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                    </div>
                    <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-1">
                      아직 내용이 없습니다
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 max-w-[200px]">
                      대화를 시작하면 여기에 문서가 만들어집니다
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Reset Confirmation Modal */}
        {showResetConfirm && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
              <div className="p-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <svg className="w-5 h-5 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                    {currentPhase === 'research_definition' ? '연구 정의' : '실험 설계'} 초기화
                  </h3>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
                  초기화할 항목을 선택하세요. 이 작업은 되돌릴 수 없습니다.
                </p>

                <div className="space-y-3 mb-6">
                  <button
                    onClick={() => handleReset('all')}
                    disabled={resetProcess.isPending}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-red-200 dark:border-red-800/50 bg-red-50 dark:bg-red-950/30 hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-lg bg-red-100 dark:bg-red-900/50 flex items-center justify-center">
                      <svg className="w-4 h-4 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </div>
                    <div>
                      <p className="font-medium text-red-700 dark:text-red-300">전체 초기화</p>
                      <p className="text-xs text-red-600/70 dark:text-red-400/70">대화 내용과 문서 모두 삭제</p>
                    </div>
                  </button>

                  <button
                    onClick={() => handleReset('messages')}
                    disabled={resetProcess.isPending}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center">
                      <svg className="w-4 h-4 text-slate-600 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                      </svg>
                    </div>
                    <div>
                      <p className="font-medium text-slate-700 dark:text-slate-300">대화만 초기화</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">대화 내용만 삭제 (문서 유지)</p>
                    </div>
                  </button>

                  <button
                    onClick={() => handleReset('artifact')}
                    disabled={resetProcess.isPending}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center">
                      <svg className="w-4 h-4 text-slate-600 dark:text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div>
                      <p className="font-medium text-slate-700 dark:text-slate-300">문서만 초기화</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">문서만 삭제 (대화 유지)</p>
                    </div>
                  </button>
                </div>

                <button
                  onClick={() => setShowResetConfirm(false)}
                  disabled={resetProcess.isPending}
                  className="w-full py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </SidebarLayout>
  );
}
