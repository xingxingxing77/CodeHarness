"use client";

/** Markdown 渲染管线（rag-web MarkdownAnswer 对齐）：rehype-highlight + gfm。 */

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

export function MarkdownAnswer({ content }: { content: string }) {
  return (
    <div className="text-[14px] leading-[1.65] text-ink [&_a]:text-accent-ink [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-3 [&_blockquote]:text-ink-2 [&_code]:rounded-[4px] [&_code]:bg-inset [&_code]:px-1 [&_code]:font-mono [&_code]:text-[12.5px] [&_h2]:mt-4 [&_h2]:text-[16px] [&_h2]:font-medium [&_h3]:mt-3 [&_h3]:text-[14px] [&_h3]:font-medium [&_li]:ml-4 [&_li]:list-disc [&_ol_li]:list-decimal [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_strong]:font-semibold [&_table]:w-full [&_table]:text-[12.5px] [&_th]:border-b [&_th]:border-line [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border-b [&_td]:border-line [&_td]:px-2 [&_td]:py-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: ({ children, ...props }) => (
            <pre className="hljs rounded-[8px] border border-line" {...props}>
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
