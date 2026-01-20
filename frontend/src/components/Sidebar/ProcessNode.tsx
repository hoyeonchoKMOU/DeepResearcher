'use client';

import { useRouter } from 'next/navigation';

interface ProcessInfo {
  id: 'research' | 'literature-org' | 'literature-search' | 'paper';
  name: string;
  icon: string;
  locked: boolean;
}

interface ProcessNodeProps {
  projectId: string;
  process: ProcessInfo;
  isActive: boolean;
  completionStatus?: {
    researchDefinition: boolean;
    experimentDesign: boolean;
  };
}

export function ProcessNode({
  projectId,
  process,
  isActive,
  completionStatus,
}: ProcessNodeProps) {
  const router = useRouter();

  const handleClick = () => {
    if (process.locked) return;
    router.push(`/project/${projectId}/${process.id}`);
  };

  // Get completion badges for Research & Experiment
  const renderCompletionBadges = () => {
    if (!completionStatus) return null;

    return (
      <div className="flex items-center gap-1 ml-auto">
        {/* Research Definition */}
        <span
          className={`text-[9px] px-1.5 py-0.5 rounded ${
            completionStatus.researchDefinition
              ? 'bg-emerald-900/50 text-emerald-400'
              : 'bg-slate-700 text-slate-400'
          }`}
          title={
            completionStatus.researchDefinition
              ? '연구 정의: 완료'
              : '연구 정의: 진행 중'
          }
        >
          RD{completionStatus.researchDefinition && ' ✓'}
        </span>
        {/* Experiment Design */}
        <span
          className={`text-[9px] px-1.5 py-0.5 rounded ${
            completionStatus.experimentDesign
              ? 'bg-emerald-900/50 text-emerald-400'
              : 'bg-slate-700 text-slate-400'
          }`}
          title={
            completionStatus.experimentDesign
              ? '실험 설계: 완료'
              : '실험 설계: 대기 중'
          }
        >
          ED{completionStatus.experimentDesign && ' ✓'}
        </span>
      </div>
    );
  };

  return (
    <button
      onClick={handleClick}
      disabled={process.locked}
      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-all duration-200 ${
        process.locked
          ? 'opacity-50 cursor-not-allowed text-slate-500'
          : isActive
          ? 'bg-primary-600/20 text-primary-400 ring-1 ring-primary-500/30'
          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-300'
      }`}
      title={
        process.locked
          ? '연구 정의와 실험 설계를 모두 완료하면 해금됩니다'
          : process.name
      }
    >
      {/* Process Icon */}
      <span className="text-sm shrink-0">{process.icon}</span>

      {/* Process Name */}
      <span className="truncate flex-1">{process.name}</span>

      {/* Completion Badges or Lock Icon */}
      {process.locked ? (
        <svg
          className="w-3.5 h-3.5 shrink-0 text-slate-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
          />
        </svg>
      ) : (
        renderCompletionBadges()
      )}
    </button>
  );
}
