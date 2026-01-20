'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { SidebarLayout, LockedOverlay } from '@/components/shared';
import {
  projectApi,
  literatureSearchApi,
  PaperEntry,
  AutoSearchResponse,
} from '@/lib/api-v3';

// ============================================================================
// Components
// ============================================================================

function SearchResultCard({
  paper,
  onAddToOrganization,
  isAdding,
  isAdded,
}: {
  paper: PaperEntry;
  onAddToOrganization: () => void;
  isAdding: boolean;
  isAdded: boolean;
}) {
  return (
    <div className={`p-4 rounded-lg border transition-colors ${
      isAdded
        ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-700'
        : 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700'
    }`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-slate-900 dark:text-white">
            {paper.title || '제목 없음'}
          </h4>
          <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 dark:text-slate-400">
            <span className="px-1.5 py-0.5 bg-slate-200 dark:bg-slate-700 rounded">
              {paper.source}
            </span>
            <span>{paper.year || '연도 미상'}</span>
          </div>
          {paper.authors && paper.authors.length > 0 && (
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1 truncate">
              {paper.authors.slice(0, 3).join(', ')}
              {paper.authors.length > 3 && '...'}
            </p>
          )}
          {paper.abstract && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 line-clamp-2">
              {paper.abstract}
            </p>
          )}
        </div>
        <button
          onClick={onAddToOrganization}
          disabled={isAdding || isAdded}
          className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 ${
            isAdded
              ? 'bg-emerald-600 text-white cursor-default'
              : 'bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50'
          }`}
        >
          {isAdded ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
              추가됨
            </>
          ) : isAdding ? (
            <>
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              추가 중...
            </>
          ) : (
            '문헌 정리에 추가'
          )}
        </button>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================
export default function LiteratureSearchPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSources, setSelectedSources] = useState<string[]>(['semantic_scholar', 'arxiv']);
  const [addingPaperId, setAddingPaperId] = useState<string | null>(null);
  const [addedPaperIds, setAddedPaperIds] = useState<Set<string>>(new Set());
  const [autoSearchResult, setAutoSearchResult] = useState<AutoSearchResponse | null>(null);

  // Fetch project status
  const { data: projectStatus, isLoading: loadingStatus } = useQuery({
    queryKey: ['project-status', projectId],
    queryFn: () => projectApi.getStatus(projectId),
    refetchInterval: 5000,
  });

  // Check if Literature Search is accessible
  const isLocked = !(projectStatus?.research_definition_complete && projectStatus?.experiment_design_complete);

  // Fetch literature search state
  const { data: searchState, isLoading: loadingSearch } = useQuery({
    queryKey: ['literature-search', projectId],
    queryFn: () => literatureSearchApi.getState(projectId),
    enabled: !isLocked,
  });

  // Search papers mutation
  const searchPapers = useMutation({
    mutationFn: (query: string) => literatureSearchApi.search(projectId, query, selectedSources),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['literature-search', projectId] });
    },
  });

  // Add to organization mutation
  const addToOrganization = useMutation({
    mutationFn: (paperId: string) => literatureSearchApi.addToOrganization(projectId, paperId),
    onSuccess: (_, paperId) => {
      queryClient.invalidateQueries({ queryKey: ['literature-search', projectId] });
      queryClient.invalidateQueries({ queryKey: ['literature-organization', projectId] });
      // Mark paper as added
      setAddedPaperIds((prev) => new Set(prev).add(paperId));
      setAddingPaperId(null);
    },
    onError: () => {
      setAddingPaperId(null);
    },
  });

  // Auto search mutation
  const autoSearch = useMutation({
    mutationFn: () => literatureSearchApi.autoSearch(projectId, selectedSources),
    onSuccess: (data) => {
      setAutoSearchResult(data);
      queryClient.invalidateQueries({ queryKey: ['literature-search', projectId] });
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      searchPapers.mutate(searchQuery.trim());
    }
  };

  const handleAddToOrganization = (paperId: string) => {
    setAddingPaperId(paperId);
    addToOrganization.mutate(paperId);
  };

  const toggleSource = (source: string) => {
    setSelectedSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source]
    );
  };

  const searchedPapers = searchState?.searched_papers || [];

  // Loading state
  if (loadingStatus || loadingSearch) {
    return (
      <SidebarLayout currentProjectId={projectId} currentProcess="literature-search">
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
    <SidebarLayout currentProjectId={projectId} currentProcess="literature-search">
      <div className="relative h-full flex flex-col bg-slate-50 dark:bg-slate-900">
        {/* Locked Overlay */}
        {isLocked && (
          <LockedOverlay processType="literature_search" projectId={projectId} />
        )}

        {/* Header */}
        <header className="shrink-0 bg-white dark:bg-slate-800 border-b border-slate-200/50 dark:border-slate-700/50 px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
                문헌 검색
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                학술 데이터베이스에서 논문 검색
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500 dark:text-slate-400">검색 소스:</span>
              {['semantic_scholar', 'arxiv', 'google_scholar'].map((source) => (
                <button
                  key={source}
                  onClick={() => toggleSource(source)}
                  disabled={isLocked}
                  className={`px-2 py-1 rounded-md transition-colors ${
                    selectedSources.includes(source)
                      ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300'
                      : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
                  } disabled:opacity-50`}
                >
                  {source === 'semantic_scholar' ? 'S2' : source === 'arxiv' ? 'arXiv' : 'GS'}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* Search Bar */}
        <div className="shrink-0 px-4 sm:px-6 py-4 border-b border-slate-200/50 dark:border-slate-700/50 bg-white/50 dark:bg-slate-800/50">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="검색어 입력 (예: machine learning security, IoT vulnerability)"
              disabled={isLocked}
              className="flex-1 px-4 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={isLocked || !searchQuery.trim() || searchPapers.isPending || selectedSources.length === 0}
              className="px-6 py-2.5 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {searchPapers.isPending ? (
                <span className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  검색 중...
                </span>
              ) : (
                '검색'
              )}
            </button>
            <button
              type="button"
              onClick={() => autoSearch.mutate()}
              disabled={isLocked || autoSearch.isPending || selectedSources.length === 0}
              className="px-4 py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              title="연구 정의 + 실험 설계 MD 기반 자동 검색"
            >
              {autoSearch.isPending ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  분석 중...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  자동 검색
                </>
              )}
            </button>
          </form>
          {/* Auto Search Info */}
          {autoSearchResult && (
            <div className="mt-3 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-200 dark:border-emerald-700">
              <div className="flex items-start gap-2">
                <span className="text-emerald-600 dark:text-emerald-400">⚡</span>
                <div className="flex-1">
                  <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
                    자동 검색 완료
                  </p>
                  <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
                    기반: {autoSearchResult.from_research_definition ? '연구 정의 ✓' : ''}
                    {autoSearchResult.from_experiment_design ? ' 실험 설계 ✓' : ''}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {autoSearchResult.queries_generated.map((query, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 bg-emerald-100 dark:bg-emerald-800/40 text-emerald-700 dark:text-emerald-300 rounded text-xs"
                      >
                        {query}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => setAutoSearchResult(null)}
                  className="text-emerald-500 hover:text-emerald-700 dark:hover:text-emerald-300"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {/* Search Results */}
          <div>
            <h3 className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
              검색 결과 ({searchedPapers.length}건)
            </h3>

            {searchedPapers.length === 0 ? (
              <div className="text-center py-12">
                <div className="text-4xl mb-4">🔍</div>
                <p className="text-slate-500 dark:text-slate-400">
                  검색 결과가 없습니다
                </p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  검색어를 입력하여 논문을 찾아보세요
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {searchedPapers.map((paper) => (
                  <SearchResultCard
                    key={paper.id}
                    paper={paper}
                    onAddToOrganization={() => handleAddToOrganization(paper.id)}
                    isAdding={addingPaperId === paper.id}
                    isAdded={addedPaperIds.has(paper.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </SidebarLayout>
  );
}
