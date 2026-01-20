'use client';

import { useRouter } from 'next/navigation';

interface LockedOverlayProps {
  processType: 'literature_review' | 'literature_search' | 'paper_writing';
  projectId: string;
}

const UNLOCK_INFO = {
  literature_review: {
    title: '문헌 검토가 잠겨 있습니다',
    description:
      '연구 정의를 완료하면 문헌 검토 기능이 해금됩니다. 해금 후에는 논문 검색, PDF 업로드, 문헌 관리 기능을 사용할 수 있습니다.',
    buttonText: '연구 정의로 이동',
    redirectPath: 'research',
    icon: '📚',
    requirement: '연구 정의 완료',
  },
  literature_search: {
    title: '문헌 검색이 잠겨 있습니다',
    description:
      '연구 정의와 실험 설계를 모두 완료하면 문헌 검색 기능이 해금됩니다. 해금 후에는 Semantic Scholar, arXiv 등에서 논문을 검색할 수 있습니다.',
    buttonText: '연구 & 실험으로 이동',
    redirectPath: 'research',
    icon: '🔍',
    requirement: '연구 정의 + 실험 설계 완료',
  },
  paper_writing: {
    title: '논문 작성이 잠겨 있습니다',
    description:
      '연구 정의와 실험 설계를 모두 완료하면 논문 작성 기능이 해금됩니다. 해금 후에는 AI의 도움을 받아 IMRAD 구조의 논문을 작성할 수 있습니다.',
    buttonText: '연구 & 실험으로 이동',
    redirectPath: 'research',
    icon: '📝',
    requirement: '연구 정의 + 실험 설계 완료',
  },
};

export function LockedOverlay({ processType, projectId }: LockedOverlayProps) {
  const router = useRouter();
  const info = UNLOCK_INFO[processType];

  const handleRedirect = () => {
    router.push(`/project/${projectId}/${info.redirectPath}`);
  };

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-slate-900/90 backdrop-blur-sm">
      <div className="max-w-md w-full mx-4 text-center">
        {/* Lock Icon */}
        <div className="relative mb-6 inline-block">
          <div className="w-20 h-20 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center">
            <span className="text-4xl">{info.icon}</span>
          </div>
          <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-slate-700 border-2 border-slate-900 flex items-center justify-center">
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
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
          </div>
        </div>

        {/* Title */}
        <h2 className="text-xl font-bold text-white mb-3">{info.title}</h2>

        {/* Description */}
        <p className="text-slate-400 text-sm mb-6 leading-relaxed">
          {info.description}
        </p>

        {/* Unlock Requirement */}
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-slate-800 rounded-full text-sm text-slate-300 mb-6">
          <svg
            className="w-4 h-4 text-amber-500"
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
          <span>해금 조건: {info.requirement}</span>
        </div>

        {/* Action Button */}
        <div>
          <button
            onClick={handleRedirect}
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 hover:bg-primary-700 text-white rounded-xl font-medium transition-colors duration-200"
          >
            {info.buttonText}
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
                d="M13 7l5 5m0 0l-5 5m5-5H6"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
