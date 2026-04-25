"use client";

import { useState } from "react";
import { Pin, PinOff, Pencil, Trash2, MoreVertical, Settings2 } from "lucide-react";
import { Conversation, User } from "@/lib/types";
import MiesLogo from "@/components/ui/MiesLogo";

interface SidebarProps {
  conversations: Conversation[];
  currentId: string | null;
  user: User | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onPin: (id: string) => void;
  onEdit: (id: string) => void;
  hasDraft: boolean;
  draftLabel: string;
  onResumeDraft: () => void;
  onDeleteDraft: () => void;
  onLogout: () => void;
  onOpenSettings: () => void;
}

export default function Sidebar({
  conversations,
  currentId,
  user,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onPin,
  onEdit,
  hasDraft,
  draftLabel,
  onResumeDraft,
  onDeleteDraft,
  onLogout,
  onOpenSettings,
}: SidebarProps) {
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const displayName = user?.name?.trim() || user?.email || "Account";
  const initial = (displayName[0] || "?").toUpperCase();

  const sorted = [...conversations].sort((a, b) => {
    if (a.pinned && !b.pinned) return -1;
    if (!a.pinned && b.pinned) return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const startRename = (conv: Conversation) => {
    setRenaming(conv.id);
    setRenameValue(conv.title);
    setMenuOpen(null);
  };

  const submitRename = (id: string) => {
    if (renameValue.trim()) {
      onRename(id, renameValue.trim());
    }
    setRenaming(null);
  };

  return (
    <div className="w-[280px] h-screen bg-[#f5f5f7] border-r border-black/[0.06] flex flex-col p-4 shrink-0 font-ui">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mb-4 px-2">
        <div className="w-8 h-8 flex items-center justify-center shrink-0">
          <MiesLogo size={18} />
        </div>
        <span className="font-['Major_Mono_Display'] text-[15px] text-[#1c1c1e] tracking-[-0.5px] leading-none">
          Mies
        </span>
      </div>

      {/* New conversation */}
      <button
        onClick={onNew}
        className="w-full bg-[#1c1c1e] text-[#f5f5f7] text-[14px] font-medium rounded-none py-2.5 mb-4 hover:bg-[#2c2c2e] transition-colors"
      >
        + Nuevo proyecto
      </button>

      {/* Draft section */}
      {hasDraft && (
        <>
          <div className="h-px bg-black/[0.06] mb-3 mt-1" />
          <p className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase px-2 mb-2">
            Borrador
          </p>
          <div className="mb-3 flex items-center gap-1">
            <button
              onClick={onResumeDraft}
              className="flex-1 text-left text-[13px] text-[#48484a] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors truncate border border-dashed border-black/[0.12]"
            >
              {draftLabel}
            </button>
            <button
              onClick={onDeleteDraft}
              aria-label="Eliminar borrador"
              className="text-[#86868b] hover:text-red-500 p-1.5 rounded-none hover:bg-black/[0.04] transition-colors shrink-0"
            >
              <Trash2 size={14} strokeWidth={2} />
            </button>
          </div>
        </>
      )}

      {/* Divider */}
      <div className="h-px bg-black/[0.06] mb-3" />

      {/* Label */}
      <p className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase px-2 mb-2">
        Proyectos
      </p>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {sorted.length === 0 ? (
          <p className="text-[13px] text-[#86868b] px-2 mt-2">
            Sin proyectos
          </p>
        ) : (
          sorted.map((conv) => (
            <div key={conv.id} className="mb-1">
              <div className="flex items-center gap-1">
                {/* Title button */}
                <button
                  onClick={() => onSelect(conv.id)}
                  className={`flex-1 text-left text-[13px] px-3 py-2 rounded-none truncate transition-colors flex items-center gap-1.5
                    ${currentId === conv.id
                      ? "bg-black/[0.08] text-[#1c1c1e] font-medium"
                      : "text-[#48484a] hover:bg-black/[0.04]"
                    }`}
                >
                  {conv.pinned && (
                    <Pin
                      size={12}
                      strokeWidth={2}
                      className="shrink-0 text-[#86868b]"
                    />
                  )}
                  <span className="truncate">{conv.title}</span>
                </button>

                {/* Three-dot menu */}
                <button
                  onClick={() =>
                    setMenuOpen(menuOpen === conv.id ? null : conv.id)
                  }
                  aria-label="Conversation actions"
                  className="text-[#86868b] hover:text-[#1c1c1e] hover:bg-black/[0.04] rounded-none p-1.5 transition-colors shrink-0"
                >
                  <MoreVertical size={16} strokeWidth={2} />
                </button>
              </div>

              {/* Dropdown menu */}
              {menuOpen === conv.id && (
                <div className="ml-2 mt-1 bg-white border border-black/[0.08] rounded-none shadow-[0_4px_20px_rgba(0,0,0,0.1)] p-1">
                  <button
                    onClick={() => {
                      onPin(conv.id);
                      setMenuOpen(null);
                    }}
                    className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors flex items-center gap-2"
                  >
                    {conv.pinned ? (
                      <PinOff size={14} strokeWidth={2} />
                    ) : (
                      <Pin size={14} strokeWidth={2} />
                    )}
                    {conv.pinned ? "Desfijar" : "Fijar"}
                  </button>
                  <button
                    onClick={() => {
                      onEdit(conv.id);
                      setMenuOpen(null);
                    }}
                    className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors flex items-center gap-2"
                  >
                    <Settings2 size={14} strokeWidth={2} />
                    Editar proyecto
                  </button>
                  <button
                    onClick={() => startRename(conv)}
                    className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors flex items-center gap-2"
                  >
                    <Pencil size={14} strokeWidth={2} />
                    Renombrar
                  </button>
                  <button
                    onClick={() => {
                      onDelete(conv.id);
                      setMenuOpen(null);
                    }}
                    className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-red-50 hover:text-red-500 transition-colors flex items-center gap-2"
                  >
                    <Trash2 size={14} strokeWidth={2} />
                    Eliminar
                  </button>
                </div>
              )}

              {/* Rename input */}
              {renaming === conv.id && (
                <div className="mt-1 ml-2">
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitRename(conv.id);
                      if (e.key === "Escape") setRenaming(null);
                    }}
                    className="w-full bg-white text-[#1c1c1e] border border-black/[0.1] rounded-none px-3 py-2 text-[13px] outline-none focus:border-black/25"
                  />
                  <div className="flex gap-2 mt-1.5">
                    <button
                      onClick={() => submitRename(conv.id)}
                      className="flex-1 bg-[#1c1c1e] text-white text-[12px] font-medium rounded-none py-1.5 hover:bg-[#2c2c2e] transition-colors"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setRenaming(null)}
                      className="flex-1 bg-black/[0.05] text-[#1c1c1e] text-[12px] font-medium rounded-none py-1.5 hover:bg-black/[0.08] transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* User chip + menu */}
      <div className="mt-3 pt-3 border-t border-black/[0.06] relative">
        {userMenuOpen && (
          <div className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-black/[0.08] rounded-none shadow-[0_4px_20px_rgba(0,0,0,0.1)] p-1">
            <button
              onClick={() => {
                setUserMenuOpen(false);
                onOpenSettings();
              }}
              className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors"
            >
              Settings
            </button>
            <button
              onClick={() => {
                setUserMenuOpen(false);
                onLogout();
              }}
              className="w-full text-left text-[13px] text-[#1c1c1e] px-3 py-2 rounded-none hover:bg-black/[0.04] transition-colors"
            >
              Log out
            </button>
          </div>
        )}
        <button
          onClick={() => setUserMenuOpen((v) => !v)}
          className="w-full flex items-center gap-2.5 px-2 py-2 rounded-none hover:bg-black/[0.04] transition-colors text-left"
        >
          <div className="w-8 h-8 rounded-none bg-[#1c1c1e] flex items-center justify-center text-white font-semibold text-[13px] shrink-0">
            {initial}
          </div>
          <span className="text-[13px] text-[#1c1c1e] font-medium truncate">
            {displayName}
          </span>
        </button>
      </div>
    </div>
  );
}
