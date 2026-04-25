"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check } from "lucide-react";
import { Message as MessageType, Attachment } from "@/lib/types";
import { api } from "@/lib/api";

interface MessageProps {
  message: MessageType;
  onCopy: (content: string) => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIconFor(mime: string): string {
  if (mime.startsWith("image/")) return "🖼";
  if (mime === "application/pdf") return "📄";
  if (mime.includes("word")) return "📝";
  if (mime === "text/markdown") return "📝";
  return "📎";
}

/**
 * Tailwind class overrides for react-markdown's default elements so the
 * rendered output fits the existing message typography without pulling
 * in @tailwindcss/typography.
 */
const markdownComponents = {
  h1: (props: any) => (
    <h1
      className="text-[22px] font-semibold text-[#1c1c1e] tracking-[-0.4px] mt-5 mb-2 first:mt-0"
      {...props}
    />
  ),
  h2: (props: any) => (
    <h2
      className="text-[19px] font-semibold text-[#1c1c1e] tracking-[-0.3px] mt-5 mb-2 first:mt-0"
      {...props}
    />
  ),
  h3: (props: any) => (
    <h3
      className="text-[16px] font-semibold text-[#1c1c1e] mt-4 mb-2 first:mt-0"
      {...props}
    />
  ),
  h4: (props: any) => (
    <h4
      className="text-[15px] font-semibold text-[#1c1c1e] mt-3 mb-1.5 first:mt-0"
      {...props}
    />
  ),
  p: (props: any) => (
    <p className="text-[15px] leading-relaxed text-[#1c1c1e] my-3 first:mt-0 last:mb-0" {...props} />
  ),
  ul: (props: any) => (
    <ul className="list-disc pl-6 my-3 space-y-1 text-[15px] text-[#1c1c1e]" {...props} />
  ),
  ol: (props: any) => (
    <ol className="list-decimal pl-6 my-3 space-y-1 text-[15px] text-[#1c1c1e]" {...props} />
  ),
  li: (props: any) => <li className="leading-relaxed" {...props} />,
  strong: (props: any) => (
    <strong className="font-semibold text-[#1c1c1e]" {...props} />
  ),
  em: (props: any) => <em className="italic" {...props} />,
  code: ({ inline, className, children, ...props }: any) =>
    inline ? (
      <code
        className="px-1.5 py-0.5 rounded-none bg-black/[0.05] text-[13px] font-mono text-[#1c1c1e]"
        {...props}
      >
        {children}
      </code>
    ) : (
      <pre className="my-3 p-3 rounded-none bg-[#f5f5f7] text-[13px] font-mono text-[#1c1c1e] overflow-x-auto">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    ),
  blockquote: (props: any) => (
    <blockquote
      className="my-3 pl-3 border-l-[3px] border-black/[0.12] text-[#48484a] italic"
      {...props}
    />
  ),
  a: (props: any) => (
    <a
      className="text-[#1c1c1e] underline underline-offset-2 hover:text-black"
      target="_blank"
      rel="noopener noreferrer"
      {...props}
    />
  ),
  hr: (props: any) => (
    <hr className="my-4 border-t border-black/[0.08]" {...props} />
  ),
  table: (props: any) => (
    <div className="my-3 overflow-x-auto">
      <table className="border-collapse text-[14px]" {...props} />
    </div>
  ),
  th: (props: any) => (
    <th
      className="border border-black/[0.08] bg-[#f5f5f7] px-3 py-1.5 font-semibold text-left"
      {...props}
    />
  ),
  td: (props: any) => (
    <td className="border border-black/[0.08] px-3 py-1.5 align-top" {...props} />
  ),
};

export default function Message({ message, onCopy }: MessageProps) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const isUser = message.role === "user";
  const inputs = (message.attachments || []).filter((a) => a.kind === "input");
  const generated = (message.attachments || []).filter(
    (a) => a.kind === "generated"
  );

  const handleCopy = () => {
    onCopy(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownload = async (att: Attachment) => {
    setDownloading(att.id);
    try {
      await api.downloadAttachment(att.id, att.filename);
    } catch (e: any) {
      console.error("Download failed:", e);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div
      className={`group flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
    >
      <div
        className={`flex flex-col ${
          isUser ? "items-end max-w-[70%]" : "items-start w-full"
        }`}
      >
        {/* Input attachment chips (user side) */}
        {isUser && inputs.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2 justify-end">
            {inputs.map((att) => (
              <button
                key={att.id}
                onClick={() => handleDownload(att)}
                disabled={downloading === att.id}
                className="flex items-center gap-2 bg-white border border-black/[0.08] rounded-none pl-2.5 pr-3 py-1.5 text-[12px] text-[#1c1c1e] hover:bg-black/[0.02] transition-colors disabled:opacity-50"
              >
                <span>{fileIconFor(att.mime_type)}</span>
                <span className="font-medium truncate max-w-[200px]">
                  {att.filename}
                </span>
                <span className="text-[#86868b]">
                  {formatBytes(att.size_bytes)}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Bubble (user) / markdown (assistant, full width) */}
        {isUser ? (
          <div className="px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap bg-[#E9E9EB] text-[#1c1c1e] rounded-none">
            {message.content}
          </div>
        ) : (
          <div className="w-full font-serif-answer">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Generated document cards (assistant side) */}
        {!isUser && generated.length > 0 && (
          <div className="mt-3 flex flex-col gap-2 w-full max-w-[480px]">
            {generated.map((att) => (
              <div
                key={att.id}
                className="flex items-center gap-3 bg-white border border-black/[0.08] rounded-none p-3 hover:border-black/[0.15] transition-colors"
              >
                <div className="w-10 h-10 rounded-none bg-[#f0f0f2] flex items-center justify-center text-[18px] shrink-0">
                  {fileIconFor(att.mime_type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-medium text-[#1c1c1e] truncate">
                    {att.filename}
                  </div>
                  <div className="text-[11px] text-[#86868b]">
                    {formatBytes(att.size_bytes)}
                  </div>
                </div>
                <button
                  onClick={() => handleDownload(att)}
                  disabled={downloading === att.id}
                  className="bg-[#1c1c1e] text-white text-[12px] font-medium rounded-none px-4 py-2 hover:bg-[#2c2c2e] transition-colors disabled:opacity-50 shrink-0 font-ui"
                >
                  {downloading === att.id ? "..." : "Download"}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <details className="mt-2 text-[12px] text-[#86868b]">
            <summary className="cursor-pointer hover:text-[#1c1c1e] transition-colors">
              {message.sources.length} source{message.sources.length > 1 ? "s" : ""}
            </summary>
            <div className="mt-1.5 space-y-1">
              {message.sources.map((src, i) => (
                <div key={i} className="text-[11px] text-[#86868b]">
                  <span className="font-medium">{src.source}</span> · {src.subject}{" "}
                  {src.level} · {Math.round(src.similarity * 100)}%
                </div>
              ))}
            </div>
          </details>
        )}

        {/* Action buttons - visible on hover */}
        <div className="flex gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={handleCopy}
            aria-label={copied ? "Copied" : "Copy message"}
            className="text-[#86868b] hover:text-[#1c1c1e] p-1.5 rounded-none hover:bg-black/[0.04] transition-all"
          >
            {copied ? (
              <Check size={14} strokeWidth={2} />
            ) : (
              <Copy size={14} strokeWidth={2} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
