"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Conversation } from "@/lib/types";

interface DraftData {
  address?: string;
  municipio?: string;
  ref_catastral?: string;
  building_type?: string;
  materials?: string[];
  budget?: string;
  ordenanza?: string;
}

interface ProjectIntakeModalProps {
  onClose: () => void;
  onCreated: (project: Conversation) => void;
  /** If provided, we're editing an existing project instead of creating. */
  existing?: Conversation | null;
  onUpdated?: (project: Conversation) => void;
  /** Called with current form data when the user closes without submitting. */
  onSaveDraft?: (draft: DraftData) => void;
  /** Pre-fill from a saved draft. */
  draft?: DraftData | null;
}

const BUILDING_TYPES = [
  "Vivienda unifamiliar",
  "Vivienda plurifamiliar",
  "Reforma integral",
  "Ampliación",
  "Oficinas",
  "Industrial",
  "Comercial",
  "Equipamiento",
  "Otro",
];

const MATERIAL_OPTIONS = [
  "Hormigón armado",
  "Acero",
  "Madera",
  "Ladrillo",
  "Bloque",
  "Mixta",
];

export default function ProjectIntakeModal({
  onClose,
  onCreated,
  existing,
  onUpdated,
  onSaveDraft,
  draft,
}: ProjectIntakeModalProps) {
  const isEditing = !!existing;

  const [address, setAddress] = useState(existing?.address || draft?.address || "");
  const [municipio, setMunicipio] = useState(existing?.municipio || draft?.municipio || "");
  const [refCatastral, setRefCatastral] = useState(
    existing?.catastro_data?.ref_catastral ||
    draft?.ref_catastral ||
    ""
  );
  const [buildingType, setBuildingType] = useState(existing?.building_type || draft?.building_type || "");
  const [materials, setMaterials] = useState<string[]>(existing?.main_materials || draft?.materials || []);
  const [customMaterial, setCustomMaterial] = useState("");
  const [budget, setBudget] = useState(existing?.estimated_budget?.toString() || draft?.budget || "");
  const [ordenanza, setOrdenanza] = useState(existing?.ordenanza || draft?.ordenanza || "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasAnyData =
    address.trim() || municipio.trim() || refCatastral.trim() || buildingType || materials.length > 0 || budget || ordenanza;

  const handleClose = () => {
    // Save draft if the user filled in anything and didn't submit
    if (!isEditing && hasAnyData && onSaveDraft) {
      onSaveDraft({
        address: address.trim(),
        municipio: municipio.trim(),
        ref_catastral: refCatastral.trim(),
        building_type: buildingType,
        materials,
        budget,
        ordenanza,
      });
    }
    onClose();
  };

  // Separate known materials from custom ones for display
  const knownMaterials = materials.filter((m) => MATERIAL_OPTIONS.includes(m));
  const customMaterials = materials.filter((m) => !MATERIAL_OPTIONS.includes(m));

  const toggleMaterial = (m: string) => {
    setMaterials((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
    );
  };

  const addCustomMaterial = () => {
    const trimmed = customMaterial.trim();
    if (trimmed && !materials.includes(trimmed)) {
      setMaterials((prev) => [...prev, trimmed]);
      setCustomMaterial("");
    }
  };

  const removeCustomMaterial = (m: string) => {
    setMaterials((prev) => prev.filter((x) => x !== m));
  };

  const canSubmit =
    address.trim().length > 0 &&
    municipio.trim().length > 0 &&
    refCatastral.trim().length >= 14;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setLoading(true);

    try {
      if (isEditing && existing && onUpdated) {
        const updated = await api.updateProject(existing.id, {
          address: address.trim(),
          municipio: municipio.trim(),
          building_type: buildingType || undefined,
          main_materials: materials.length > 0 ? materials : undefined,
          estimated_budget: budget ? parseFloat(budget) : undefined,
          ordenanza: ordenanza.trim() || undefined,
        });
        onUpdated(updated);
      } else {
        const project = await api.createProject({
          address: address.trim(),
          municipio: municipio.trim(),
          ref_catastral: refCatastral.trim(),
          building_type: buildingType || undefined,
          main_materials: materials,
          estimated_budget: budget ? parseFloat(budget) : undefined,
          ordenanza: ordenanza.trim() || undefined,
        });
        onCreated(project);
      }
    } catch (e: any) {
      setError(e?.message || "Error al guardar el proyecto");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center px-6 overflow-y-auto py-10"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-[560px] bg-white rounded-none shadow-[0_20px_60px_rgba(0,0,0,0.25)] p-6 font-ui"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-[20px] font-semibold text-[#1c1c1e] tracking-[-0.3px]">
            {isEditing ? "Editar proyecto" : "Nuevo proyecto"}
          </h2>
          <button
            onClick={handleClose}
            className="text-[#86868b] hover:text-[#1c1c1e] text-[20px] leading-none w-8 h-8 rounded-none hover:bg-black/[0.04] transition-colors"
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <div className="flex flex-col gap-4">
          {/* Address — required */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Dirección completa <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Calle, número, provincia"
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
            />
          </div>

          {/* Municipio — required */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Municipio <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={municipio}
              onChange={(e) => setMunicipio(e.target.value)}
              placeholder="Ej: Málaga"
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
            />
          </div>

          {/* Referencia catastral — required */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Referencia catastral <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={refCatastral}
              onChange={(e) => setRefCatastral(e.target.value.toUpperCase())}
              placeholder="14 o 20 caracteres. Ej: 8937004TP8293N"
              maxLength={20}
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] font-mono placeholder:text-[#86868b] placeholder:font-sans outline-none focus:border-black/20 transition-colors"
            />
          </div>

          {/* Building type — optional */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Tipo de edificación
            </label>
            <select
              value={buildingType}
              onChange={(e) => setBuildingType(e.target.value)}
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] outline-none focus:border-black/20 transition-colors appearance-none"
            >
              <option value="">Sin especificar</option>
              {BUILDING_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {/* Materials — optional */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-2 block">
              Materiales principales
            </label>
            <div className="flex flex-wrap gap-2 mb-2">
              {MATERIAL_OPTIONS.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => toggleMaterial(m)}
                  className={`px-4 py-2 text-[13px] rounded-none transition-all
                    ${
                      materials.includes(m)
                        ? "bg-[#1c1c1e] text-white font-medium"
                        : "bg-[#f5f5f7] text-[#48484a] border border-black/[0.08] hover:bg-[#e8e8ed]"
                    }`}
                >
                  {m}
                </button>
              ))}
            </div>

            {/* Custom materials */}
            {customMaterials.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {customMaterials.map((m) => (
                  <div
                    key={m}
                    className="flex items-center gap-1.5 bg-[#1c1c1e] text-white text-[13px] font-medium px-3 py-1.5 rounded-none"
                  >
                    <span>{m}</span>
                    <button
                      onClick={() => removeCustomMaterial(m)}
                      className="text-white/60 hover:text-white text-[14px] leading-none"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add custom material */}
            <div className="flex gap-2">
              <input
                type="text"
                value={customMaterial}
                onChange={(e) => setCustomMaterial(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addCustomMaterial();
                  }
                }}
                placeholder="Otro material..."
                className="flex-1 bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-3 py-2 text-[13px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
              />
              <button
                type="button"
                onClick={addCustomMaterial}
                disabled={!customMaterial.trim()}
                className="bg-[#f5f5f7] text-[#48484a] border border-black/[0.08] rounded-none px-3 py-2 text-[13px] hover:bg-[#e8e8ed] transition-colors disabled:opacity-30"
              >
                Añadir
              </button>
            </div>
          </div>

          {/* Budget — optional */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Presupuesto estimado (EUR)
            </label>
            <input
              type="number"
              min="0"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              placeholder="—"
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
            />
          </div>

          {/* Ordenanza específica — optional */}
          <div>
            <label className="text-[11px] font-medium text-[#86868b] tracking-[1.5px] uppercase mb-1.5 block">
              Ordenanza específica
            </label>
            <input
              type="text"
              value={ordenanza}
              onChange={(e) => setOrdenanza(e.target.value)}
              placeholder="Ej: Ordenanza de zona residencial R-3"
              className="w-full bg-[#f5f5f7] text-[#1c1c1e] border border-black/[0.08] rounded-none px-4 py-3 text-[14px] placeholder:text-[#86868b] outline-none focus:border-black/20 transition-colors"
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-[13px] text-red-500">{error}</p>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || loading}
            className="w-full bg-[#1c1c1e] text-white font-medium text-[15px] rounded-none py-3.5 mt-2 hover:scale-[1.02] transition-all disabled:opacity-30 disabled:hover:scale-100"
          >
            {loading
              ? isEditing
                ? "Guardando..."
                : "Creando proyecto..."
              : isEditing
              ? "Guardar cambios"
              : "Crear proyecto"}
          </button>
        </div>
      </div>
    </div>
  );
}
