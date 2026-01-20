'use client';

interface PhaseIndicatorProps {
  currentPhase: 'research_definition' | 'experiment_design';
  researchDefinitionComplete: boolean;
  experimentDesignComplete: boolean;
  onSwitchPhase: (phase: 'research_definition' | 'experiment_design') => void;
  onComplete: () => void;
  isCompleting?: boolean;
}

export function PhaseIndicator({
  currentPhase,
  researchDefinitionComplete,
  experimentDesignComplete,
  onSwitchPhase,
  onComplete,
  isCompleting = false,
}: PhaseIndicatorProps) {
  // Determine what gets unlocked when completing current phase
  const getUnlockInfo = (phaseId: 'research_definition' | 'experiment_design') => {
    if (phaseId === 'research_definition') {
      // Research Definition completion unlocks Literature Review
      // And if Experiment Design is already complete, also unlocks Paper Writing
      if (experimentDesignComplete) {
        return { unlocks: '문헌 검토 & 논문 작성', unlocksParticle: '이' };
      }
      return { unlocks: '문헌 검토', unlocksParticle: '가' };
    } else {
      // Experiment Design completion
      // If Research Definition is already complete, unlocks Paper Writing
      // Otherwise, shows that both are needed
      if (researchDefinitionComplete) {
        return { unlocks: '논문 작성', unlocksParticle: '이' };
      }
      return { unlocks: '(연구 정의 완료 시) 논문 작성', unlocksParticle: '이' };
    }
  };

  const phases = [
    {
      id: 'research_definition' as const,
      name: '연구 정의',
      shortName: '연구 정의',
      icon: '💡',
      complete: researchDefinitionComplete,
      ...getUnlockInfo('research_definition'),
      nameParticle: '를', // 연구 정의 ends in vowel
    },
    {
      id: 'experiment_design' as const,
      name: '실험 설계',
      shortName: '실험 설계',
      icon: '🔬',
      complete: experimentDesignComplete,
      ...getUnlockInfo('experiment_design'),
      nameParticle: '를', // 실험 설계 ends in vowel
    },
  ];

  const currentPhaseInfo = phases.find((p) => p.id === currentPhase);
  const isCurrentPhaseComplete =
    currentPhase === 'research_definition'
      ? researchDefinitionComplete
      : experimentDesignComplete;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-4">
      {/* Phase Tabs */}
      <div className="flex items-center gap-2 mb-4">
        {phases.map((phase, index) => {
          const isActive = phase.id === currentPhase;

          return (
            <div key={phase.id} className="flex items-center">
              <button
                onClick={() => onSwitchPhase(phase.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300 ring-1 ring-primary-200 dark:ring-primary-800'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <span>{phase.icon}</span>
                <span className="hidden sm:inline">{phase.name}</span>
                <span className="sm:hidden">{phase.shortName}</span>
                {phase.complete && (
                  <svg
                    className="w-4 h-4 text-emerald-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2.5}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                )}
              </button>
              {index < phases.length - 1 && (
                <svg
                  className="w-4 h-4 mx-1 text-slate-300 dark:text-slate-600"
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
              )}
            </div>
          );
        })}
      </div>

      {/* Complete Button & Status */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          {isCurrentPhaseComplete ? (
            <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
              <svg
                className="w-4 h-4 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span>
                {currentPhaseInfo?.name} 완료 - {currentPhaseInfo?.unlocks}{' '}
                해금됨
              </span>
            </div>
          ) : (
            <div className="text-sm text-slate-500 dark:text-slate-400">
              <span className="hidden sm:inline">
                {currentPhaseInfo?.name}{currentPhaseInfo?.nameParticle} 완료하면{' '}
                {currentPhaseInfo?.unlocks}{currentPhaseInfo?.unlocksParticle} 해금됩니다
              </span>
              <span className="sm:hidden">
                완료 시 {currentPhaseInfo?.unlocks} 해금
              </span>
            </div>
          )}
        </div>

        <button
          onClick={onComplete}
          disabled={isCompleting || isCurrentPhaseComplete}
          className={`shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
            isCurrentPhaseComplete
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 cursor-default'
              : 'bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
          }`}
        >
          {isCompleting ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
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
              <span>처리 중...</span>
            </>
          ) : isCurrentPhaseComplete ? (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span>완료됨</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"
                />
              </svg>
              <span className="hidden sm:inline">완료하고 다음 단계 해금</span>
              <span className="sm:hidden">완료</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
