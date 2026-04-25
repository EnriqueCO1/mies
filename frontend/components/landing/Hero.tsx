"use client";

import { useState, useMemo } from "react";
import Link from "next/link";

/* ── Grid generation (runs once at module level) ── */

function scatter(seed: number, count: number, min: number, max: number): number[] {
  const positions: number[] = [0];
  let h = seed;
  for (let i = 0; i < count; i++) {
    h = ((h * 2654435761) >>> 0) ^ ((h >>> 16) * 0x45d9f3b);
    h = (h >>> 0);
    positions.push(positions[positions.length - 1] + min + (h % (max - min)));
  }
  return positions;
}

const BASE_XS = scatter(7919, 22, 40, 120);
const BASE_YS = scatter(6271, 14, 35, 80);
const MAX_X = BASE_XS[BASE_XS.length - 1];
const MAX_Y = BASE_YS[BASE_YS.length - 1];
const SQ = 5;
const PUSH = 14;

/* ── Component ── */

export default function Hero() {
  const [hovered, setHovered] = useState<{ col: number; row: number } | null>(null);

  // Compute the translate offset for each column / row line.
  // The hovered cell's 4 bounding lines push outward; everything else stays.
  const xOffsets = useMemo(
    () =>
      BASE_XS.map((_, i) => {
        if (!hovered) return 0;
        if (i === hovered.col) return -PUSH;
        if (i === hovered.col + 1) return PUSH;
        return 0;
      }),
    [hovered]
  );

  const yOffsets = useMemo(
    () =>
      BASE_YS.map((_, j) => {
        if (!hovered) return 0;
        if (j === hovered.row) return -PUSH;
        if (j === hovered.row + 1) return PUSH;
        return 0;
      }),
    [hovered]
  );

  return (
    <section className="relative min-h-[700px] flex items-center justify-center pt-36 pb-20 px-12 overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0">
        <svg
          viewBox={`-20 -20 ${MAX_X + 40} ${MAX_Y + 40}`}
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid slice"
        >
          {/* Layer 1: vertical lines — translate horizontally */}
          {BASE_XS.map((x, i) => (
            <line
              key={`v${i}`}
              x1={x} y1={-20} x2={x} y2={MAX_Y + 20}
              stroke="rgba(0,0,0,0.42)"
              strokeWidth={0.5}
              style={{
                transform: `translateX(${xOffsets[i]}px)`,
                transition: "transform 0.8s cubic-bezier(0.16,1,0.3,1)",
                pointerEvents: "none",
              }}
            />
          ))}

          {/* Layer 1b: horizontal lines — translate vertically */}
          {BASE_YS.map((y, j) => (
            <line
              key={`h${j}`}
              x1={-20} y1={y} x2={MAX_X + 20} y2={y}
              stroke="rgba(0,0,0,0.42)"
              strokeWidth={0.5}
              style={{
                transform: `translateY(${yOffsets[j]}px)`,
                transition: "transform 0.8s cubic-bezier(0.16,1,0.3,1)",
                pointerEvents: "none",
              }}
            />
          ))}

          {/* Layer 2: invisible cell hit targets (at BASE positions) */}
          {BASE_XS.slice(0, -1).map((_, col) =>
            BASE_YS.slice(0, -1).map((_, row) => (
              <rect
                key={`c${col}-${row}`}
                x={BASE_XS[col]}
                y={BASE_YS[row]}
                width={BASE_XS[col + 1] - BASE_XS[col]}
                height={BASE_YS[row + 1] - BASE_YS[row]}
                fill="transparent"
                stroke="none"
                onMouseEnter={() => setHovered({ col, row })}
                onMouseLeave={() => setHovered(null)}
              />
            ))
          )}

          {/* Layer 3: intersection squares — translate with their line offsets */}
          {BASE_XS.map((x, i) =>
            BASE_YS.map((y, j) => (
              <rect
                key={`d${i}-${j}`}
                x={x - SQ / 2}
                y={y - SQ / 2}
                width={SQ}
                height={SQ}
                fill="white"
                stroke="rgba(0,0,0,0.42)"
                strokeWidth={0.75}
                style={{
                  transform: `translate(${xOffsets[i]}px, ${yOffsets[j]}px)`,
                  transition: "transform 0.8s cubic-bezier(0.16,1,0.3,1)",
                  pointerEvents: "none",
                }}
              />
            ))
          )}
        </svg>
      </div>

      {/* Typography */}
      <div className="relative z-10 flex flex-col items-center text-center max-w-[960px] pointer-events-none">
        <div className="font-mono text-[11px] font-medium text-[#86868b] tracking-[2px] uppercase mb-12 animate-[fadeUp_0.9s_cubic-bezier(0.16,1,0.3,1)_0.15s_both]">
          Asistente de arquitectura con IA
        </div>

        <div className="animate-[fadeUp_0.9s_cubic-bezier(0.16,1,0.3,1)_0.25s_both]">
          <span className="font-['Outfit'] font-bold text-[clamp(42px,7vw,88px)] text-[#86868b] tracking-[-4px] leading-[0.95] uppercase">
            Proyecta
          </span>
          <span className="font-['Outfit'] font-bold text-[clamp(48px,8vw,96px)] text-[#1c1c1e] tracking-[-4px] leading-[0.95] uppercase ml-4">
            Mejor.
          </span>
        </div>

        <div className="animate-[fadeUp_0.9s_cubic-bezier(0.16,1,0.3,1)_0.4s_both]">
          <span className="font-['Outfit'] font-bold text-[clamp(36px,5.5vw,72px)] text-[#86868b] tracking-[-4px] leading-[0.95] uppercase">
            Construye
          </span>
          <span className="font-['Outfit'] font-bold text-[clamp(48px,8vw,96px)] text-[#1c1c1e] tracking-[-4px] leading-[0.95] uppercase ml-5">
            Más rápido.
          </span>
        </div>

        <p className="text-[18px] text-[#48484a] font-normal leading-relaxed max-w-[520px] mt-10 mb-12 animate-[fadeUp_0.9s_cubic-bezier(0.16,1,0.3,1)_0.55s_both]">
          Conectado al PGOU de tu municipio, CTE, LOE, BCCA y Catastro.
          <br />
          Proyectos de ejecución precisos, con cada dato citado a su fuente.
        </p>

        <Link
          href="/register"
          className="pointer-events-auto text-[16px] font-medium text-white bg-[#1c1c1e] rounded-none px-[60px] py-[17px] font-ui hover:scale-[1.03] hover:shadow-[0_8px_40px_rgba(0,0,0,0.1)] transition-all shadow-[0_2px_20px_rgba(0,0,0,0.06)] animate-[fadeUp_0.9s_cubic-bezier(0.16,1,0.3,1)_0.65s_both]"
        >
          Empieza gratis
        </Link>
      </div>

      {/* Scroll hint */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 animate-[fadeIn_1s_ease_1.5s_both]">
        <span className="text-[11px] text-[#86868b] tracking-[1px] uppercase">
          Descubre
        </span>
        <div className="w-px h-8 bg-gradient-to-b from-[#86868b] to-transparent animate-[pulse_2s_ease-in-out_infinite]" />
      </div>
    </section>
  );
}
