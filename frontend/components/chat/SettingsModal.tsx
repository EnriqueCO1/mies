"use client";

import { useState } from "react";
import { User } from "@/lib/types";

interface SettingsModalProps {
  user: User | null;
  onClose: () => void;
  onDeleteAccount: () => Promise<void>;
}

export default function SettingsModal({
  user,
  onClose,
  onDeleteAccount,
}: SettingsModalProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    setError(null);
    setDeleting(true);
    try {
      await onDeleteAccount();
      // Parent will unmount the modal on success.
    } catch (e: any) {
      setError(e?.message || "Failed to delete account");
      setDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center px-6"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[480px] bg-white rounded-none shadow-[0_20px_60px_rgba(0,0,0,0.25)] p-6 font-ui"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-[20px] font-semibold text-[#1c1c1e] tracking-[-0.3px]">
            Settings
          </h2>
          <button
            onClick={onClose}
            className="text-[#86868b] hover:text-[#1c1c1e] text-[20px] leading-none w-8 h-8 rounded-none hover:bg-black/[0.04] transition-colors"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Account info */}
        <div className="mb-6">
          <p className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-2">
            Account
          </p>
          <div className="bg-[#f5f5f7] rounded-none p-4 text-[13px] text-[#1c1c1e] space-y-1">
            <div>
              <span className="text-[#86868b]">Nombre: </span>
              {user?.name || "—"}
            </div>
            <div>
              <span className="text-[#86868b]">Email: </span>
              {user?.email || "—"}
            </div>
            <div>
              <span className="text-[#86868b]">Colegiado: </span>
              {user?.colegiado_number || "—"}
            </div>
          </div>
        </div>

        {/* Danger zone */}
        <div className="border-t border-black/[0.06] pt-5">
          <p className="text-[11px] font-medium text-red-500 tracking-[1.5px] uppercase mb-2">
            Danger zone
          </p>

          {!confirming ? (
            <button
              onClick={() => setConfirming(true)}
              className="w-full text-left bg-red-50 hover:bg-red-100 text-red-600 rounded-none px-4 py-3 text-[14px] font-medium transition-colors"
            >
              Delete account
            </button>
          ) : (
            <div className="bg-red-50 rounded-none p-4">
              <p className="text-[13px] text-[#1c1c1e] mb-3">
                This permanently deletes your account and all conversations.
                This action cannot be undone.
              </p>
              {error && (
                <p className="text-[12px] text-red-600 mb-3">{error}</p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white text-[13px] font-medium rounded-none py-2.5 transition-colors disabled:opacity-50"
                >
                  {deleting ? "Deleting..." : "Yes, delete my account"}
                </button>
                <button
                  onClick={() => {
                    setConfirming(false);
                    setError(null);
                  }}
                  disabled={deleting}
                  className="flex-1 bg-white hover:bg-black/[0.04] text-[#1c1c1e] text-[13px] font-medium rounded-none py-2.5 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
