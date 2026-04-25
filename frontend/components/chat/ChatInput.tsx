"use client";

import { useState, useRef, useEffect, useImperativeHandle } from "react";

/**
 * Imperative handle the chat page uses to push text back into the input
 * — for example when the user hits Stop mid-generation, so their message
 * is restored exactly as they typed it.
 */
export interface ChatInputHandle {
  restore: (text: string) => void;
}

interface ChatInputProps {
  onSend: (message: string, files: File[]) => void;
  disabled?: boolean;
  // When provided and `disabled` is true, the send button turns into a
  // stop button that invokes this callback (aborting the in-flight turn).
  onStop?: () => void;
  // React 19 ref-as-prop. Exposes `restore(text)`.
  ref?: React.Ref<ChatInputHandle>;
}

// Keep these in sync with backend/app/services/files.py
const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "text/plain",
  "text/markdown",
  "image/png",
  "image/jpeg",
];
const ACCEPT_ATTR = ".pdf,.txt,.md,.png,.jpg,.jpeg,application/pdf,text/plain,text/markdown,image/png,image/jpeg";
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const MAX_FILES = 3;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ChatInput({ onSend, disabled, onStop, ref }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Expose imperative methods to the parent (chat page).
  useImperativeHandle(
    ref,
    () => ({
      restore: (text: string) => {
        setValue(text);
        // Give React a tick to render the new value, then focus and push
        // the caret to the end so the user can keep editing in place.
        requestAnimationFrame(() => {
          const ta = textareaRef.current;
          if (ta) {
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);
          }
        });
      },
    }),
    [],
  );

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  }, [value]);

  const handleSubmit = () => {
    if ((!value.trim() && files.length === 0) || disabled) return;
    onSend(value.trim(), files);
    setValue("");
    setFiles([]);
    setError(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFilesPicked = (picked: FileList | null) => {
    if (!picked || picked.length === 0) return;
    const next = [...files];
    const errors: string[] = [];

    for (const f of Array.from(picked)) {
      if (next.length >= MAX_FILES) {
        errors.push(`Maximum ${MAX_FILES} files per message.`);
        break;
      }
      if (f.size > MAX_FILE_BYTES) {
        errors.push(
          `${f.name} is larger than ${MAX_FILE_BYTES / (1024 * 1024)} MB.`
        );
        continue;
      }
      // Some browsers report "" for .md files — be lenient on extension.
      const typeOk =
        ACCEPTED_MIME_TYPES.includes(f.type) ||
        /\.(pdf|txt|md|png|jpe?g)$/i.test(f.name);
      if (!typeOk) {
        errors.push(`${f.name}: unsupported file type.`);
        continue;
      }
      next.push(f);
    }

    setFiles(next);
    setError(errors.length ? errors.join(" ") : null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const canSubmit = (value.trim().length > 0 || files.length > 0) && !disabled;

  return (
    <div className="border-t border-black/[0.06] p-4 font-ui">
      <div className="max-w-[800px] mx-auto flex flex-col gap-2">
        {/* File chips */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {files.map((f, i) => (
              <div
                key={`${f.name}-${i}`}
                className="flex items-center gap-2 bg-[#f0f0f2] border border-black/[0.06] rounded-none pl-3 pr-2 py-1.5 text-[12px] text-[#1c1c1e]"
              >
                <span className="font-medium truncate max-w-[200px]">
                  {f.name}
                </span>
                <span className="text-[#86868b]">{formatBytes(f.size)}</span>
                <button
                  onClick={() => removeFile(i)}
                  className="text-[#86868b] hover:text-[#1c1c1e] leading-none text-[16px] w-4 h-4 flex items-center justify-center"
                  aria-label={`Remove ${f.name}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-[12px] text-red-500">{error}</p>
        )}

        {/* Input row */}
        <div className="flex items-end gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_ATTR}
            onChange={(e) => handleFilesPicked(e.target.files)}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || files.length >= MAX_FILES}
            aria-label="Attach files"
            className="bg-[#f0f0f2] text-[#48484a] hover:text-[#1c1c1e] rounded-none p-3 transition-colors disabled:opacity-30 shrink-0 border border-transparent hover:border-black/[0.08]"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            rows={1}
            disabled={disabled}
            className="flex-1 bg-[#f0f0f2] text-[#1c1c1e] rounded-none px-5 py-3.5 text-[15px] resize-none outline-none placeholder:text-[#86868b] border border-transparent focus:border-black/[0.08] transition-colors disabled:opacity-50"
          />
          {disabled && onStop ? (
            <button
              onClick={onStop}
              aria-label="Stop"
              className="relative bg-[#1c1c1e] text-white rounded-none p-3 hover:bg-[#2c2c2e] transition-colors shrink-0"
            >
              {/* Marching-ants dotted outline — shrunk a touch so there's a
                  visible black gap between it and the white glyph inside.
                  Four edge gradients (top/bottom/left/right) with a 3px
                  dash + 3px gap give the "dotted" look; the marchingAnts
                  keyframe slides their positions so the dashes travel
                  around the rectangle. */}
              <span
                aria-hidden
                className="absolute inset-[9px] pointer-events-none animate-[marchingAnts_0.55s_linear_infinite]"
                style={{
                  backgroundImage: `
                    linear-gradient(90deg, currentColor 50%, transparent 50%),
                    linear-gradient(90deg, currentColor 50%, transparent 50%),
                    linear-gradient(0deg,  currentColor 50%, transparent 50%),
                    linear-gradient(0deg,  currentColor 50%, transparent 50%)
                  `,
                  backgroundPosition:
                    "0 0, 0 100%, 0 0, 100% 0",
                  backgroundRepeat:
                    "repeat-x, repeat-x, repeat-y, repeat-y",
                  backgroundSize:
                    "6px 1px, 6px 1px, 1px 6px, 1px 6px",
                }}
              />
              {/* White filled inner glyph — slightly enlarged so it sits
                  with a clear gap inside the dotted outline. */}
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="white"
                stroke="none"
                className="relative"
              >
                <rect x="3" y="3" width="18" height="18" />
              </svg>
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              aria-label="Send"
              className="bg-[#1c1c1e] text-white rounded-none p-3 hover:bg-[#2c2c2e] transition-colors disabled:opacity-30 shrink-0"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
