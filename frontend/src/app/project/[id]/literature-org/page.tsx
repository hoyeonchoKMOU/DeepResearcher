'use client';

import { useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { KoreanMarkdown } from '@/components/KoreanMarkdown';
import { SidebarLayout } from '@/components/shared';
import {
  projectApi,
  literatureOrganizationApi,
  PaperEntry,
} from '@/lib/api-v3';

// ============================================================================
// Components
// ============================================================================

function PaperCard({
  paper,
  isSelected,
  onClick,
  onDelete,
}: {
  paper: PaperEntry;
  isSelected: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  // Status display configuration
  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'completed':
        return { label: '완료', className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' };
      case 'processing':
        return { label: '처리 중', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300', spinning: true };
      case 'pending_download':
      case 'downloading':
        return { label: 'PDF 다운로드', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300', spinning: true };
      case 'failed':
        return { label: '실패', className: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' };
      default:
        return { label: '대기', className: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400' };
    }
  };

  const statusConfig = getStatusConfig(paper.status);
  const hasFullText = paper.full_text && paper.full_text.length > 100;

  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-lg cursor-pointer transition-all duration-200 ${
        isSelected
          ? 'bg-primary-100 dark:bg-primary-900/40 ring-1 ring-primary-300 dark:ring-primary-700'
          : 'bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-slate-900 dark:text-white truncate">
            {paper.title || '제목 없음'}
          </h4>
          <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 dark:text-slate-400">
            <span>{paper.type === 'upload' ? '📤' : '🔍'}</span>
            <span>{paper.year || '연도 미상'}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] flex items-center gap-1 ${statusConfig.className}`}>
              {statusConfig.spinning && (
                <svg className="w-2.5 h-2.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {statusConfig.label}
            </span>
          </div>
          {/* Full text indicator */}
          {hasFullText && paper.status === 'pending' && (
            <div className="flex items-center gap-1 mt-1.5 text-[10px] text-emerald-600 dark:text-emerald-400">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              전문 포함
            </div>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-1 text-slate-400 hover:text-red-500 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}

function AddPaperModal({
  isOpen,
  onClose,
  onAdd,
  isAdding,
}: {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (paper: Partial<PaperEntry> & { full_text?: string }) => void;
  isAdding: boolean;
}) {
  const [title, setTitle] = useState('');
  const [authors, setAuthors] = useState('');
  const [year, setYear] = useState('');
  const [abstract, setAbstract] = useState('');
  const [fullText, setFullText] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd({
      title,
      authors: authors.split(',').map((a) => a.trim()).filter(Boolean),
      year: year ? parseInt(year) : undefined,
      abstract,
      full_text: fullText || undefined,
    });
    setTitle('');
    setAuthors('');
    setYear('');
    setAbstract('');
    setFullText('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-6 m-4">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">
          논문 직접 추가
        </h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              제목 *
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                저자 (쉼표로 구분)
              </label>
              <input
                type="text"
                value={authors}
                onChange={(e) => setAuthors(e.target.value)}
                placeholder="홍길동, 김철수"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                연도
              </label>
              <input
                type="number"
                value={year}
                onChange={(e) => setYear(e.target.value)}
                min="1900"
                max="2099"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              초록
            </label>
            <textarea
              value={abstract}
              onChange={(e) => setAbstract(e.target.value)}
              rows={3}
              placeholder="논문의 초록을 입력하세요"
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              논문 텍스트 (선택사항)
            </label>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
              논문 전문을 입력하면 더 정확한 요약이 생성됩니다
            </p>
            <textarea
              value={fullText}
              onChange={(e) => setFullText(e.target.value)}
              rows={8}
              placeholder="논문 전문을 붙여넣기 하세요..."
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500 resize-y font-mono"
            />
            {fullText && (
              <p className="text-xs text-slate-400 mt-1">
                {fullText.length.toLocaleString()}자 입력됨
              </p>
            )}
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg font-medium hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={!title || isAdding}
              className="flex-1 px-4 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isAdding ? '추가 중...' : '논문 추가'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UploadingModal({ filename }: { filename: string }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-2xl shadow-2xl p-6 m-4">
        <div className="flex flex-col items-center">
          {/* Animated upload icon */}
          <div className="relative w-16 h-16 mb-4">
            <svg
              className="w-16 h-16 text-primary-500 animate-pulse"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            {/* Spinning ring */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-20 h-20 border-4 border-primary-200 dark:border-primary-800 border-t-primary-500 rounded-full animate-spin" />
            </div>
          </div>

          <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
            PDF 업로드 중
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 text-center mb-4 truncate max-w-full px-4">
            {filename}
          </p>

          {/* Progress bar animation */}
          <div className="w-full h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-primary-500 to-primary-600 rounded-full animate-progress" />
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-2">
            잠시만 기다려 주세요...
          </p>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================
export default function LiteratureOrganizationPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const queryClient = useQueryClient();

  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [uploadingFilename, setUploadingFilename] = useState<string>('');
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch project status
  const { data: projectStatus, isLoading: loadingStatus } = useQuery({
    queryKey: ['project-status', projectId],
    queryFn: () => projectApi.getStatus(projectId),
    refetchInterval: 5000,
  });

  // Fetch literature organization state - always enabled (no lock)
  const { data: litState, isLoading: loadingLit } = useQuery({
    queryKey: ['literature-organization', projectId],
    queryFn: () => literatureOrganizationApi.getState(projectId),
  });

  // Add paper mutation
  const addPaper = useMutation({
    mutationFn: (paper: Partial<PaperEntry>) =>
      literatureOrganizationApi.addPaper(projectId, paper),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
      setShowAddModal(false);
    },
  });

  // Delete paper mutation
  const deletePaper = useMutation({
    mutationFn: (paperId: string) =>
      literatureOrganizationApi.deletePaper(projectId, paperId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
      if (selectedPaperId) setSelectedPaperId(null);
    },
  });

  // Process paper mutation
  const processPaper = useMutation({
    mutationFn: (paperId: string) =>
      literatureOrganizationApi.processPaper(projectId, paperId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
    },
  });

  // Upload PDF mutation
  const uploadPdf = useMutation({
    mutationFn: (file: File) => literatureOrganizationApi.uploadPdf(projectId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
    },
  });

  // Reset mutation
  const resetLiterature = useMutation({
    mutationFn: () => literatureOrganizationApi.reset(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
      setShowResetConfirm(false);
      setSelectedPaperId(null);
    },
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setUploadingFilename(file.name);
      uploadPdf.mutate(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const papers = litState?.papers || [];
  const selectedPaper = papers.find((p) => p.id === selectedPaperId);

  // Loading state
  if (loadingStatus || loadingLit) {
    return (
      <SidebarLayout currentProjectId={projectId} currentProcess="literature-org">
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

  return (
    <SidebarLayout currentProjectId={projectId} currentProcess="literature-org">
      <div className="relative h-full flex flex-col bg-slate-50 dark:bg-slate-900">
        {/* No lock overlay - Literature Organization is always accessible */}

        {/* Header */}
        <header className="shrink-0 bg-white dark:bg-slate-800 border-b border-slate-200/50 dark:border-slate-700/50 px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
                문헌 정리
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                총 {papers.length}편의 논문 | PDF 업로드 및 MD 변환
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* Reset Button */}
              {papers.length > 0 && (
                <button
                  onClick={() => setShowResetConfirm(true)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 rounded-lg text-sm font-medium hover:bg-red-200 dark:hover:bg-red-800/50 transition-colors"
                  title="전체 초기화"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                  초기화
                </button>
              )}
              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                논문 추가
              </button>
              <label className="flex items-center gap-2 px-3 py-1.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 cursor-pointer transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
                PDF 업로드
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileUpload}
                  disabled={uploadPdf.isPending}
                  className="hidden"
                />
              </label>
            </div>
          </div>
        </header>

        {/* Main Content - 2 Column Layout */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel - Paper List */}
          <div className="w-72 shrink-0 border-r border-slate-200/50 dark:border-slate-700/50 overflow-y-auto p-4 space-y-2">
            {papers.length === 0 ? (
              <div className="text-center py-8">
                <div className="text-3xl mb-2">📁</div>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  아직 논문이 없습니다
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  PDF를 업로드하여 시작하세요
                </p>
              </div>
            ) : (
              papers.map((paper) => (
                <PaperCard
                  key={paper.id}
                  paper={paper}
                  isSelected={paper.id === selectedPaperId}
                  onClick={() => setSelectedPaperId(paper.id)}
                  onDelete={() => deletePaper.mutate(paper.id)}
                />
              ))
            )}
          </div>

          {/* Center Panel - Paper Preview */}
          <div className="flex-1 overflow-y-auto p-6 bg-white dark:bg-slate-800">
            {selectedPaper ? (
              <div>
                {/* Header with title and action button */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                      {selectedPaper.title}
                    </h2>
                    {selectedPaper.authors && selectedPaper.authors.length > 0 && (
                      <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        {selectedPaper.authors.join(', ')}
                      </p>
                    )}
                    {selectedPaper.year && (
                      <p className="text-sm text-slate-500 dark:text-slate-400">
                        {selectedPaper.year}
                      </p>
                    )}
                  </div>
                  {selectedPaper.status === 'pending' && (
                    <button
                      onClick={() => processPaper.mutate(selectedPaper.id)}
                      disabled={processPaper.isPending}
                      className="px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                    >
                      {processPaper.isPending ? '처리 중...' : 'MD로 변환'}
                    </button>
                  )}
                  {selectedPaper.status === 'completed' && (
                    <div className="flex items-center gap-2">
                      <span className="px-3 py-1.5 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 rounded-lg text-sm font-medium">
                        처리됨
                      </span>
                      <button
                        onClick={() => literatureOrganizationApi.downloadPaperMD(projectId, selectedPaper.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                        title="MD 파일 다운로드"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                          />
                        </svg>
                        MD 다운로드
                      </button>
                    </div>
                  )}
                </div>

                {/* Content based on status */}
                {(selectedPaper.status === 'pending_download' || selectedPaper.status === 'downloading') && (
                  <div className="flex flex-col items-center justify-center py-12">
                    <div className="relative">
                      <svg className="w-12 h-12 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" />
                      </svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-16 h-16 border-4 border-amber-200 dark:border-amber-800 border-t-amber-500 rounded-full animate-spin" />
                      </div>
                    </div>
                    <p className="text-amber-600 dark:text-amber-400 font-medium mt-4">
                      PDF 다운로드 중...
                    </p>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
                      논문 전문을 다운로드하고 있습니다
                    </p>
                    {selectedPaper.abstract && (
                      <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-200 dark:border-slate-700 max-w-xl">
                        <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase mb-2">초록</h4>
                        <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-4">
                          {selectedPaper.abstract}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {selectedPaper.status === 'processing' && (
                  <div className="flex flex-col items-center justify-center py-12">
                    <svg className="w-8 h-8 animate-spin text-primary-500 mb-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <p className="text-slate-500 dark:text-slate-400">논문 처리 중...</p>
                  </div>
                )}

                {selectedPaper.status === 'failed' && (
                  <div className="flex flex-col items-center justify-center py-12">
                    <div className="text-4xl mb-4">x</div>
                    <p className="text-red-500 font-medium">처리에 실패했습니다</p>
                    <button
                      onClick={() => processPaper.mutate(selectedPaper.id)}
                      className="mt-4 px-4 py-2 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
                    >
                      다시 시도
                    </button>
                  </div>
                )}

                {selectedPaper.status === 'completed' && selectedPaper.md_content ? (
                  <div className="prose prose-slate dark:prose-invert prose-sm max-w-none">
                    <KoreanMarkdown>{selectedPaper.md_content}</KoreanMarkdown>
                  </div>
                ) : selectedPaper.status === 'pending' && (
                  <>
                    {/* Full text indicator */}
                    {selectedPaper.full_text && selectedPaper.full_text.length > 100 && (
                      <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 rounded-lg flex items-center gap-2">
                        <svg className="w-5 h-5 text-emerald-600 dark:text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div>
                          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
                            논문 전문이 포함되어 있습니다
                          </p>
                          <p className="text-xs text-emerald-600 dark:text-emerald-400">
                            {(selectedPaper.full_text.length / 1000).toFixed(1)}KB의 텍스트가 요약에 사용됩니다
                          </p>
                        </div>
                      </div>
                    )}
                    {selectedPaper.abstract && (
                      <div className="prose prose-slate dark:prose-invert prose-sm max-w-none">
                        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
                          초록
                        </h3>
                        <p className="text-slate-600 dark:text-slate-400">
                          {selectedPaper.abstract}
                        </p>
                      </div>
                    )}
                    <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-200 dark:border-slate-700">
                      <p className="text-sm text-slate-500 dark:text-slate-400 text-center">
                        "MD로 변환"을 클릭하여 이 논문의 상세 요약을 생성하세요
                      </p>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-4xl mb-4">📄</div>
                <p className="text-slate-500 dark:text-slate-400">
                  목록에서 논문을 선택하면 상세 내용을 볼 수 있습니다
                </p>
              </div>
            )}
          </div>

        </div>

        {/* Add Paper Modal */}
        <AddPaperModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onAdd={(paper) => addPaper.mutate(paper)}
          isAdding={addPaper.isPending}
        />

        {/* Uploading Modal */}
        {uploadPdf.isPending && <UploadingModal filename={uploadingFilename} />}

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
                    문헌 정리 초기화
                  </h3>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
                  모든 논문({papers.length}개)이 삭제됩니다. 이 작업은 되돌릴 수 없습니다.
                </p>

                <div className="flex gap-3">
                  <button
                    onClick={() => setShowResetConfirm(false)}
                    disabled={resetLiterature.isPending}
                    className="flex-1 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 rounded-lg transition-colors"
                  >
                    취소
                  </button>
                  <button
                    onClick={() => resetLiterature.mutate()}
                    disabled={resetLiterature.isPending}
                    className="flex-1 py-2.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {resetLiterature.isPending ? '삭제 중...' : '전체 삭제'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </SidebarLayout>
  );
}
