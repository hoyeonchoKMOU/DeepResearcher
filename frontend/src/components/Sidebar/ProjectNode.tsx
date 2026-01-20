'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ProcessNode } from './ProcessNode';
import { ProjectV3, projectApi } from '@/lib/api-v3';

interface ProjectNodeProps {
  project: ProjectV3;
  isActive: boolean;
  activeProcess?: 'research' | 'literature-org' | 'literature-search' | 'paper';
}

// Rename Modal
function RenameModal({
  currentTopic,
  onConfirm,
  onCancel,
  isRenaming,
}: {
  currentTopic: string;
  onConfirm: (newTopic: string) => void;
  onCancel: () => void;
  isRenaming: boolean;
}) {
  const [newTopic, setNewTopic] = useState(currentTopic);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Focus and select all text when modal opens
    if (inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (newTopic.trim() && newTopic.trim() !== currentTopic) {
      onConfirm(newTopic.trim());
    } else {
      onCancel();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />
      {/* Modal */}
      <div className="relative bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden border border-slate-700">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-primary-500/20 flex items-center justify-center">
              <svg
                className="w-5 h-5 text-primary-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">프로젝트 이름 변경</h3>
              <p className="text-sm text-slate-400">새로운 이름을 입력하세요</p>
            </div>
          </div>
        </div>
        {/* Content */}
        <form onSubmit={handleSubmit}>
          <div className="px-6 py-4">
            <input
              ref={inputRef}
              type="text"
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500 transition-all"
              placeholder="프로젝트 이름"
              disabled={isRenaming}
            />
          </div>
          {/* Actions */}
          <div className="px-6 py-4 bg-slate-900/50 flex gap-3 justify-end">
            <button
              type="button"
              onClick={onCancel}
              disabled={isRenaming}
              className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isRenaming || !newTopic.trim() || newTopic.trim() === currentTopic}
              className="px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isRenaming ? (
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
                  저장 중...
                </>
              ) : (
                '저장'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Delete Confirmation Modal
function DeleteConfirmModal({
  projectTopic,
  onConfirm,
  onCancel,
  isDeleting,
}: {
  projectTopic: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />
      {/* Modal */}
      <div className="relative bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden border border-slate-700">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
              <svg
                className="w-5 h-5 text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">프로젝트 삭제</h3>
              <p className="text-sm text-slate-400">이 작업은 되돌릴 수 없습니다</p>
            </div>
          </div>
        </div>
        {/* Content */}
        <div className="px-6 py-4">
          <p className="text-slate-300">
            <span className="font-medium text-white">"{projectTopic}"</span> 프로젝트를
            정말 삭제하시겠습니까?
          </p>
          <p className="text-sm text-slate-400 mt-2">
            모든 연구 데이터, 문헌 검토, 논문 초안이 영구적으로 삭제됩니다.
          </p>
        </div>
        {/* Actions */}
        <div className="px-6 py-4 bg-slate-900/50 flex gap-3 justify-end">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white transition-colors disabled:opacity-50"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="px-4 py-2 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {isDeleting ? (
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
                삭제 중...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
                삭제하기
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

interface ProcessInfo {
  id: 'research' | 'literature-org' | 'literature-search' | 'paper';
  name: string;
  icon: string;
  locked: boolean;
}

export function ProjectNode({
  project,
  isActive,
  activeProcess,
}: ProjectNodeProps) {
  const [isExpanded, setIsExpanded] = useState(isActive);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showRenameModal, setShowRenameModal] = useState(false);
  const router = useRouter();
  const queryClient = useQueryClient();

  // Delete mutation
  const deleteProject = useMutation({
    mutationFn: () => projectApi.deleteProject(project.project_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects-v3'] });
      setShowDeleteModal(false);
      // If we're currently viewing this project, navigate to home
      if (isActive) {
        router.push('/');
      }
    },
  });

  // Rename mutation
  const renameProject = useMutation({
    mutationFn: (newTopic: string) => projectApi.renameProject(project.project_id, newTopic),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects-v3'] });
      queryClient.invalidateQueries({ queryKey: ['project-status', project.project_id] });
      setShowRenameModal(false);
    },
  });

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent expanding/collapsing
    setShowDeleteModal(true);
  };

  const handleRenameClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent expanding/collapsing
    setShowRenameModal(true);
  };

  // Define processes with their lock status
  // v3.1: 4 processes with updated lock conditions
  const processes: ProcessInfo[] = [
    {
      id: 'research',
      name: '연구 & 실험',
      icon: '🔬',
      locked: false, // Always accessible
    },
    {
      id: 'literature-org',
      name: '문헌 정리',
      icon: '📁',
      locked: false, // Always accessible (PDF → MD)
    },
    {
      id: 'literature-search',
      name: '문헌 검색',
      icon: '🔍',
      locked: !(project.research_definition_complete && project.experiment_design_complete),
    },
    {
      id: 'paper',
      name: '논문 작성',
      icon: '📝',
      locked: !(project.research_definition_complete && project.experiment_design_complete),
    },
  ];

  // Calculate status indicator
  const getStatusIndicator = () => {
    if (project.research_definition_complete && project.experiment_design_complete) {
      return { color: 'bg-emerald-500', label: '전체 해금됨' };
    }
    if (project.research_definition_complete) {
      return { color: 'bg-blue-500', label: '진행 중' };
    }
    return { color: 'bg-slate-500', label: '시작됨' };
  };

  const status = getStatusIndicator();

  return (
    <>
      <div className="group/project" role="treeitem" aria-expanded={isExpanded}>
        {/* Project Header */}
        <div
          className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg transition-all duration-200 ${
            isActive
              ? 'bg-slate-800 text-white'
              : 'text-slate-300 hover:bg-slate-800/50 hover:text-white'
          }`}
        >
          {/* Expand/Collapse Button */}
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-2 flex-1 min-w-0 text-left"
          >
            {/* Expand/Collapse Icon */}
            <svg
              className={`w-4 h-4 shrink-0 text-slate-500 transition-transform duration-200 ${
                isExpanded ? 'rotate-90' : ''
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

            {/* Project Title */}
            <span className="flex-1 text-sm font-medium truncate">
              {project.topic}
            </span>
          </button>

          {/* Status Indicator */}
          <span
            className={`w-2 h-2 shrink-0 rounded-full ${status.color} group-hover/project:hidden`}
            title={status.label}
          />

          {/* Action Buttons (visible on hover) */}
          <div className="hidden group-hover/project:flex items-center gap-0.5">
            {/* Rename Button */}
            <button
              onClick={handleRenameClick}
              className="shrink-0 w-6 h-6 flex items-center justify-center rounded-md text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 transition-all"
              title="프로젝트 이름 변경"
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            </button>

            {/* Delete Button */}
            <button
              onClick={handleDeleteClick}
              className="shrink-0 w-6 h-6 flex items-center justify-center rounded-md text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
              title="프로젝트 삭제"
            >
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
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

        {/* Process List */}
        {isExpanded && (
          <div className="ml-4 mt-1 space-y-0.5 border-l border-slate-700 pl-2">
            {processes.map((process) => (
              <ProcessNode
                key={process.id}
                projectId={project.project_id}
                process={process}
                isActive={isActive && activeProcess === process.id}
                completionStatus={
                  process.id === 'research'
                    ? {
                        researchDefinition: project.research_definition_complete,
                        experimentDesign: project.experiment_design_complete,
                      }
                    : undefined
                }
              />
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <DeleteConfirmModal
          projectTopic={project.topic}
          onConfirm={() => deleteProject.mutate()}
          onCancel={() => setShowDeleteModal(false)}
          isDeleting={deleteProject.isPending}
        />
      )}

      {/* Rename Modal */}
      {showRenameModal && (
        <RenameModal
          currentTopic={project.topic}
          onConfirm={(newTopic) => renameProject.mutate(newTopic)}
          onCancel={() => setShowRenameModal(false)}
          isRenaming={renameProject.isPending}
        />
      )}
    </>
  );
}
