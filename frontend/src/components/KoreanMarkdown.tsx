'use client';

import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';

/**
 * Pre-process markdown text to fix Korean word boundary issues.
 *
 * CommonMark requires word boundaries (spaces) around formatting markers.
 * Korean particles (조사) attached directly after ** break parsing.
 *
 * This function inserts zero-width spaces to fix the issue.
 */
function preprocessKoreanMarkdown(text: string): string {
  if (!text) return '';

  // Fix bold: **text**한글 → **text**​한글 (zero-width space)
  // Pattern: **...** followed by Korean character without space
  let processed = text.replace(
    /(\*\*[^*]+\*\*)([가-힣])/g,
    '$1\u200B$2'  // Insert zero-width space
  );

  // Fix italic: *text*한글 → *text*​한글
  // Be careful not to match ** (bold)
  processed = processed.replace(
    /(?<!\*)(\*[^*]+\*)(?!\*)([가-힣])/g,
    '$1\u200B$2'
  );

  // Fix bold: 한글**text** → 한글​**text**
  processed = processed.replace(
    /([가-힣])(\*\*[^*]+\*\*)/g,
    '$1\u200B$2'
  );

  // Fix italic: 한글*text* → 한글​*text*
  processed = processed.replace(
    /([가-힣])(?<!\*)(\*[^*]+\*)(?!\*)/g,
    '$1\u200B$2'
  );

  return processed;
}

interface KoreanMarkdownProps {
  children: string;
  className?: string;
  components?: Components;
}

/**
 * Markdown component optimized for Korean text.
 *
 * Handles word boundary issues with Korean particles (조사)
 * that break CommonMark bold/italic parsing.
 *
 * Usage:
 * ```tsx
 * <KoreanMarkdown>{markdownText}</KoreanMarkdown>
 * ```
 */
export function KoreanMarkdown({ children, className, components }: KoreanMarkdownProps) {
  const processedText = preprocessKoreanMarkdown(children);

  return (
    <ReactMarkdown className={className} components={components}>
      {processedText}
    </ReactMarkdown>
  );
}

export default KoreanMarkdown;
