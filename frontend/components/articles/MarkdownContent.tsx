'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div
      className="markdown-body max-h-[60vh] overflow-auto rounded-[12px] p-4 text-sm leading-7"
      style={{ background: '#181b25', color: '#a8abb8', boxShadow: 'inset 0 0 0 1px #262933' }}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
