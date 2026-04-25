"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Conversation, Message as MessageType, User } from "@/lib/types";
import Sidebar from "@/components/chat/Sidebar";
import Message from "@/components/chat/Message";
import ChatInput, { type ChatInputHandle } from "@/components/chat/ChatInput";
import SettingsModal from "@/components/chat/SettingsModal";
import ProjectIntakeModal from "@/components/chat/ProjectIntakeModal";
import DataSourceIndicators from "@/components/chat/DataSourceIndicators";
import MiesLogo from "@/components/ui/MiesLogo";

export default function ChatPage() {
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageType[]>([]);
  const [loading, setLoading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [catastroFetching, setCatastroFetching] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  // After a reply lands, keep the tools that were actually used lit for a
  // couple of seconds so the user can see which sources Claude consulted.
  const [lastToolsUsed, setLastToolsUsed] = useState<string[]>([]);
  // Holds the AbortController for the currently in-flight chat request so
  // the stop button can cancel it. Cleared in `finally` either way.
  const abortControllerRef = useRef<AbortController | null>(null);
  // Imperative handle into the input — used by handleStop to push the
  // message text back into the textarea so the user can edit and retry.
  const chatInputRef = useRef<ChatInputHandle>(null);
  // Records whether the in-flight turn was stopped by the user, so the
  // finally block can pop the optimistic user message + restore its text
  // without racing the AbortError catch branch.
  const stoppedByUserRef = useRef(false);

  // Draft state — saved when user closes the intake form without submitting
  const [draft, setDraft] = useState<{
    address?: string;
    municipio?: string;
    ref_catastral?: string;
    building_type?: string;
    materials?: string[];
    budget?: string;
    ordenanza?: string;
  } | null>(() => {
    // Restore from localStorage on mount
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("project_draft");
        return saved ? JSON.parse(saved) : null;
      } catch { return null; }
    }
    return null;
  });

  // Check auth on mount
  useEffect(() => {
    const token = api.getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    loadConversations();
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const profile = await api.getProfile();
      setUser(profile);
    } catch {
      // Non-fatal: sidebar falls back to "Account"
    }
  };

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadConversations = async () => {
    try {
      const convs = await api.getConversations();
      setConversations(convs);
    } catch {
      // Token might be expired
      router.push("/login");
    } finally {
      setInitialLoad(false);
    }
  };

  const loadMessages = async (conversationId: string) => {
    try {
      const conv = await api.getConversation(conversationId);
      setMessages(conv.messages || []);
      setCurrentId(conversationId);
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  };

  const handleSelectConversation = (id: string) => {
    loadMessages(id);
  };

  const handleSaveDraft = (draftData: typeof draft) => {
    // Only save if there's meaningful data
    const hasData = draftData && (
      draftData.address || draftData.municipio || draftData.ref_catastral ||
      draftData.building_type ||
      (draftData.materials && draftData.materials.length > 0) ||
      draftData.budget || draftData.ordenanza
    );
    if (hasData) {
      setDraft(draftData);
      localStorage.setItem("project_draft", JSON.stringify(draftData));
    }
  };

  const clearDraft = () => {
    setDraft(null);
    localStorage.removeItem("project_draft");
  };

  const handleNewConversation = () => {
    setIntakeOpen(true);
  };

  const handleResumeDraft = () => {
    setIntakeOpen(true);
  };

  const handleProjectCreated = async (project: Conversation) => {
    setIntakeOpen(false);
    clearDraft();
    setCurrentId(project.id);
    setMessages([]);
    loadConversations();

    // Auto-fetch catastro data in the background
    if (project.address) {
      setCatastroFetching(true);
      try {
        await api.fetchCatastroData(project.id);
        loadConversations(); // refresh to pick up catastro_data
      } catch {
        // Non-fatal — catastro data is optional
      } finally {
        setCatastroFetching(false);
      }
    }
  };

  const handleSend = async (content: string, files: File[]) => {
    if (!currentId) {
      setIntakeOpen(true);
      return;
    }

    // Optimistic: add user message immediately. We don't know the real
    // attachment IDs yet, so we fake them with "pending-*" and replace
    // after the server responds by reloading the conversation.
    const optimisticInputAttachments = files.map((f, i) => ({
      id: `pending-${i}`,
      kind: "input" as const,
      filename: f.name,
      mime_type: f.type || "application/octet-stream",
      size_bytes: f.size,
    }));
    const userMsg: MessageType = {
      role: "user",
      content,
      attachments: optimisticInputAttachments,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setChatLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    stoppedByUserRef.current = false;

    // Push an empty assistant bubble immediately so text_delta events
    // can accumulate into it. The spinner stays visible until the first
    // token arrives (see `loading` state below).
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "" },
    ]);

    // Collect tools_used as tool_call events arrive so the source
    // indicators light up *while* each tool is running, not only at the
    // end of the turn.
    const liveToolsUsed = new Set<string>();
    // Map tool name → source-indicator id (search_normativa is
    // resolved at the backend into pgou/cte tags inside the final event;
    // during streaming we just light both conservatively).
    const TOOL_TO_INDICATORS: Record<string, string[]> = {
      search_normativa: ["pgou", "cte"],
      consultar_catastro: ["catastro"],
      consultar_bcca: ["bcca"],
    };

    try {
      const result = await api.sendMessageStream(
        {
          message: content,
          conversation_id: currentId || undefined,
          files,
        },
        (event) => {
          if (event.type === "text_delta") {
            // Append the chunk to the last assistant message.
            setMessages((prev) => {
              if (prev.length === 0) return prev;
              const copy = prev.slice();
              const last = copy[copy.length - 1];
              if (last.role !== "assistant") return prev;
              copy[copy.length - 1] = {
                ...last,
                content: last.content + event.text,
              };
              return copy;
            });
          } else if (event.type === "tool_call") {
            const indicators = TOOL_TO_INDICATORS[event.name] || [];
            indicators.forEach((id) => liveToolsUsed.add(id));
            setLastToolsUsed(Array.from(liveToolsUsed));
          }
        },
        controller.signal,
      );

      // `done` payload arrived. Overwrite the streamed assistant bubble
      // with the authoritative values (sources + attachments + the
      // backend's canonical `response` text — usually identical to what
      // we streamed but could differ if the last turn emitted only a
      // tool_use with no preamble, in which case we use the placeholder
      // the backend persisted).
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const copy = prev.slice();
        const last = copy[copy.length - 1];
        if (last.role !== "assistant") return prev;
        copy[copy.length - 1] = {
          role: "assistant",
          content: result.response || last.content,
          sources: result.sources,
          attachments: result.attachments,
        };
        return copy;
      });

      // Replace the "live tool_call" indicators with the backend's
      // canonical `tools_used` list, then dim after a short window.
      const finalUsed = result.tools_used || [];
      setLastToolsUsed(finalUsed);
      if (finalUsed.length > 0) {
        window.setTimeout(() => setLastToolsUsed([]), 3500);
      }

      if (!currentId) {
        setCurrentId(result.conversation_id);
      }
      if (files.length > 0) {
        // Reload so attachment IDs switch from "pending-*" to real UUIDs.
        try {
          const fresh = await api.getConversation(result.conversation_id);
          setMessages(fresh.messages || []);
        } catch {
          // non-fatal; optimistic state is still fine
        }
      }

      loadConversations();
    } catch (err: any) {
      // User-cancelled: pop the optimistic user message and push its text
      // back into the input so they can tweak it and resend. File
      // attachments aren't re-materialised (File objects aren't
      // serialisable); the user can re-attach them if needed.
      //
      // We keep the restore() call OUTSIDE the setMessages updater —
      // state updaters must be pure, and calling ChatInput's
      // setValue() from within one makes React scream
      // "Cannot update a component while rendering a different
      // component". Using the `content` closure (the exact text we
      // just sent) removes the need to look at messages at all.
      if (err?.name === "AbortError" || stoppedByUserRef.current) {
        // The streaming path pushes TWO bubbles at the start — the user
        // message and an empty assistant bubble to accumulate deltas
        // into. On abort we drop both so the UI is back to where it was.
        chatInputRef.current?.restore(content);
        setMessages((prev) => prev.slice(0, -2));
      } else {
        // Replace the empty assistant bubble we pushed before streaming
        // with the error text. (If somehow no bubble is there, append.)
        const errText = `Error: ${err.message || "Something went wrong"}`;
        setMessages((prev) => {
          const copy = prev.slice();
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = { role: "assistant", content: errText };
          } else {
            copy.push({ role: "assistant", content: errText });
          }
          return copy;
        });
      }
    } finally {
      abortControllerRef.current = null;
      stoppedByUserRef.current = false;
      setLoading(false);
      setChatLoading(false);
    }
  };

  const handleStop = () => {
    stoppedByUserRef.current = true;
    abortControllerRef.current?.abort();
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteConversation(id);
      if (currentId === id) {
        setCurrentId(null);
        setMessages([]);
      }
      loadConversations();
    } catch (err) {
      console.error("Failed to delete:", err);
    }
  };

  const handleRename = async (id: string, title: string) => {
    try {
      await api.updateProject(id, { title });
      loadConversations();
    } catch (err) {
      console.error("Failed to rename:", err);
    }
  };

  const handleEditProject = (id: string) => {
    setEditingProjectId(id);
  };

  const handleProjectUpdated = (project: Conversation) => {
    setEditingProjectId(null);
    loadConversations();
  };

  const handlePin = async (id: string) => {
    const conv = conversations.find((c) => c.id === id);
    if (!conv) return;
    try {
      await api.updateProject(id, { pinned: !conv.pinned });
      loadConversations();
    } catch (err) {
      console.error("Failed to pin:", err);
    }
  };

  const handleCopy = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const handleLogout = () => {
    // Clears the auth token only — conversations remain in the database
    // and will be reloaded on next login.
    api.logout();
    router.push("/login");
  };

  const handleDeleteAccount = async () => {
    // Permanently deletes the account and cascades conversations/messages
    // on the backend, then clears the local token and sends the user home.
    await api.deleteAccount();
    setSettingsOpen(false);
    router.push("/");
  };

  if (initialLoad) {
    return (
      <div className="h-screen bg-white flex items-center justify-center">
        <div className="text-[#86868b] text-[15px]">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-white">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        currentId={currentId}
        user={user}
        onSelect={handleSelectConversation}
        onNew={handleNewConversation}
        onDelete={handleDelete}
        onRename={handleRename}
        onPin={handlePin}
        onEdit={handleEditProject}
        hasDraft={!!draft}
        draftLabel={draft?.address ? draft.address.slice(0, 40) : "Proyecto sin guardar"}
        onResumeDraft={handleResumeDraft}
        onDeleteDraft={clearDraft}
        onLogout={handleLogout}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {settingsOpen && (
        <SettingsModal
          user={user}
          onClose={() => setSettingsOpen(false)}
          onDeleteAccount={handleDeleteAccount}
        />
      )}

      {intakeOpen && (
        <ProjectIntakeModal
          onClose={() => setIntakeOpen(false)}
          onCreated={handleProjectCreated}
          onSaveDraft={handleSaveDraft}
          draft={draft}
        />
      )}

      {editingProjectId && (
        <ProjectIntakeModal
          existing={conversations.find((c) => c.id === editingProjectId) || null}
          onClose={() => setEditingProjectId(null)}
          onCreated={() => {}}
          onUpdated={handleProjectUpdated}
        />
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col h-screen">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-8">
          <div className="max-w-[800px] mx-auto">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center pt-32">
                <div className="w-14 h-14 flex items-center justify-center mb-6">
                  <MiesLogo size={32} />
                </div>
                {currentId ? (
                  <>
                    <h2 className="text-[24px] font-semibold text-[#1c1c1e] tracking-[-0.5px] mb-2">
                      Proyecto listo
                    </h2>
                    <p className="text-[15px] text-[#86868b] max-w-[400px]">
                      Escribe tu primera consulta sobre este proyecto — normativa CTE, memorias, cálculos, lo que necesites.
                    </p>
                  </>
                ) : (
                  <>
                    <h2 className="text-[24px] font-semibold text-[#1c1c1e] tracking-[-0.5px] mb-2">
                      Crea un nuevo proyecto
                    </h2>
                    <p className="text-[15px] text-[#86868b] max-w-[400px] mb-6">
                      Para empezar, crea un proyecto con los datos de la obra.
                    </p>
                    <button
                      onClick={() => setIntakeOpen(true)}
                      className="bg-[#1c1c1e] text-white font-medium text-[14px] rounded-none px-8 py-3 font-ui hover:scale-[1.02] transition-all"
                    >
                      + Nuevo proyecto
                    </button>
                  </>
                )}
              </div>
            ) : (
              <>
                {messages.map((msg, i) => (
                  <Message key={i} message={msg} onCopy={handleCopy} />
                ))}
                {loading && (
                  <div className="flex justify-start items-center gap-3 mb-4 py-1">
                    {/* Rotating frame: four grey lines in the Hero grid's
                        shade (rgba(0,0,0,0.42)) with a 6×6 white dot
                        pinned on every corner of the big square. Each
                        dot's CENTER sits exactly on the big square's
                        corner point — half the dot inside, half outside
                        — and each line extends 3px past the corner so
                        it passes straight through the center of its two
                        corner dots. Continuous slow spin. */}
                    <div className="relative w-6 h-6 animate-spin [animation-duration:2s]">
                      {/* Big square's four edges as 2px-thick grey bands
                          straddling each corner (top:-1px + height:2px
                          centres the band on y=0). With 2px bands inside
                          the 6px dots, the pixels split evenly: 2 above
                          / 2 band / 2 below — no more "more hanging
                          outside" optical imbalance. Each band extends
                          3px past the corner on both ends so it runs
                          from the center of one corner dot to the
                          center of the next. */}
                      <div className="absolute -top-[1px] -left-[3px] -right-[3px] h-[2px] bg-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -bottom-[1px] -left-[3px] -right-[3px] h-[2px] bg-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -left-[1px] -top-[3px] -bottom-[3px] w-[2px] bg-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -right-[1px] -top-[3px] -bottom-[3px] w-[2px] bg-[rgba(0,0,0,0.42)]" />
                      {/* Corner dots — 6×6, centers at (0,0), (24,0),
                          (0,24), (24,24): exactly on each corner of the
                          big square. Drawn on top of the grey bands so
                          the bands appear to pass through the dot's
                          middle and exit the opposite side. */}
                      <div className="absolute -top-[3px] -left-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -top-[3px] -right-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -bottom-[3px] -left-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
                      <div className="absolute -bottom-[3px] -right-[3px] w-[6px] h-[6px] bg-white border border-[rgba(0,0,0,0.42)]" />
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>
        </div>

        {/* Input */}
        <ChatInput
          ref={chatInputRef}
          onSend={handleSend}
          disabled={loading}
          onStop={handleStop}
        />
        <DataSourceIndicators
          sources={[
            {
              id: "catastro",
              label: "Catastro",
              icon: (
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="12" height="10" />
                  <line x1="2" y1="7" x2="14" y2="7" />
                  <line x1="7" y1="3" x2="7" y2="13" />
                </svg>
              ),
              // Lights up while the intake form is fetching catastro data,
              // or right after a turn where Claude consulted the Catastro tool.
              active: catastroFetching || lastToolsUsed.includes("catastro"),
            },
            {
              id: "pgou",
              label: "PGOU",
              icon: (
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 2h7l3 3v9H3V2z" />
                  <path d="M10 2v3h3" />
                  <line x1="5" y1="7" x2="11" y2="7" />
                  <line x1="5" y1="9.5" x2="11" y2="9.5" />
                  <line x1="5" y1="12" x2="9" y2="12" />
                </svg>
              ),
              active: lastToolsUsed.includes("pgou"),
            },
            {
              id: "cte",
              label: "CTE",
              icon: (
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  {/* Stacked documents — CTE has several DBs */}
                  <rect x="3" y="4" width="8" height="10" />
                  <path d="M5 2h8v10" />
                  <line x1="5" y1="7" x2="9" y2="7" />
                  <line x1="5" y1="9.5" x2="9" y2="9.5" />
                  <line x1="5" y1="12" x2="8" y2="12" />
                </svg>
              ),
              active: lastToolsUsed.includes("cte"),
            },
            {
              id: "bcca",
              label: "BCCA",
              icon: (
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                  {/* Price tag — tied to precios/partidas */}
                  <path d="M8.5 2h4.5v4.5L7 13 2 8l6.5-6z" />
                  <circle cx="11" cy="4.5" r="0.8" />
                </svg>
              ),
              active: lastToolsUsed.includes("bcca"),
            },
          ]}
        />
        {/* Trust-calibration disclaimer — matches the style of the source
            indicators row above (small, muted, centred) so it reads as a
            single footer block beneath the input. */}
        <p className="text-center text-[11px] text-[#86868b] font-ui px-4 pb-3">
          Mies es IA y puede cometer errores. Por favor, verifica las respuestas.
        </p>
      </div>
    </div>
  );
}
