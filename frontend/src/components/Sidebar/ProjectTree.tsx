'use client';

import { ProjectNode } from './ProjectNode';
import { ProjectV3 } from '@/lib/api-v3';

interface ProjectTreeProps {
  projects: ProjectV3[];
  currentProjectId?: string;
  currentProcess?: 'research' | 'literature-org' | 'literature-search' | 'paper';
}

export function ProjectTree({
  projects,
  currentProjectId,
  currentProcess,
}: ProjectTreeProps) {
  // Sort projects by updated_at (most recent first)
  const sortedProjects = [...projects].sort((a, b) => {
    const dateA = new Date(a.updated_at || a.created_at).getTime();
    const dateB = new Date(b.updated_at || b.created_at).getTime();
    return dateB - dateA;
  });

  return (
    <nav className="space-y-1" role="tree" aria-label="Research Projects">
      {sortedProjects.map((project) => (
        <ProjectNode
          key={project.project_id}
          project={project}
          isActive={project.project_id === currentProjectId}
          activeProcess={
            project.project_id === currentProjectId ? currentProcess : undefined
          }
        />
      ))}
    </nav>
  );
}
