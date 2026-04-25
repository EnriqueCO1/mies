const sources = [
  {
    icon: "⊟",
    name: "PGOU",
    short: "Planes urbanísticos municipales",
    text: (
      <>
        PGOU/PGOM indexados de{" "}
        <span className="text-[#1c1c1e]">
          Málaga, Marbella, Torremolinos, Fuengirola, Mijas, Estepona,
          Nerja, Benalmádena, Alhaurín de la Torre, Rincón de la Victoria,
          Vélez-Málaga y Antequera
        </span>
        . La búsqueda se limita automáticamente al municipio del proyecto —
        nunca mezcla ordenanzas de otros.
      </>
    ),
  },
  {
    icon: "◇",
    name: "CTE",
    short: "Código Técnico completo",
    text: (
      <>
        Los seis Documentos Básicos —{" "}
        <span className="text-[#1c1c1e]">
          DB-SE, DB-SI, DB-SUA, DB-HS, DB-HR y DB-HE
        </span>{" "}
        — junto con todos los Documentos de Apoyo (DA). Cobertura integral
        del CTE vigente.
      </>
    ),
  },
  {
    icon: "○",
    name: "LOE",
    short: "Ley 38/1999",
    text: (
      <>
        Ley de Ordenación de la Edificación. Para preguntas sobre{" "}
        <span className="text-[#1c1c1e]">
          agentes, licencias, dirección facultativa, garantías decenales y
          libro del edificio
        </span>
        .
      </>
    ),
  },
  {
    icon: "⬡",
    name: "BCCA",
    short: "Base de precios oficial",
    text: (
      <>
        Banco de Coste de la Construcción de Andalucía. Precios unitarios
        reales para{" "}
        <span className="text-[#1c1c1e]">
          mediciones, partidas, PEM y PEC
        </span>{" "}
        — sin precios inventados.
      </>
    ),
  },
  {
    icon: "△",
    name: "Catastro",
    short: "INSPIRE WFS",
    text: (
      <>
        Carga automática del inmueble por referencia catastral:{" "}
        <span className="text-[#1c1c1e]">
          superficie construida, superficie gráfica, año, uso, número de
          plantas y dirección normalizada
        </span>
        .
      </>
    ),
  },
];

export default function Features() {
  return (
    <section
      className="max-w-[1200px] mx-auto py-36 px-12 max-md:py-20 max-md:px-6"
      id="features"
    >
      <div className="font-mono text-[11px] font-medium text-[#86868b] tracking-[2px] uppercase mb-5">
        Fuentes de datos
      </div>
      <h2 className="text-[clamp(32px,4vw,48px)] font-semibold text-[#1c1c1e] tracking-[-1.5px] leading-tight mb-5">
        Cinco fuentes oficiales.
        <br />
        Nunca inventadas.
      </h2>
      <p className="text-[18px] text-[#48484a] leading-relaxed max-w-[620px] mb-18">
        Cada respuesta cita de dónde sale — PGOU, CTE, LOE, BCCA o Catastro.
        Si un dato no está en ninguna de estas fuentes, Mies lo dice en
        lugar de improvisar.
      </p>

      {/* 5 cards — one per data source. 1 col on mobile, 2 on tablet,
          5 on desktop so each source gets an equal bar. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-px mt-18">
        {sources.map((s) => (
          <div
            key={s.name}
            className="bg-[#f5f5f7] p-8 hover:bg-[#e8e8ed] transition-colors flex flex-col"
          >
            <div className="w-12 h-12 rounded-none bg-black/[0.04] border border-black/[0.08] flex items-center justify-center text-[20px] mb-6">
              {s.icon}
            </div>
            <div className="text-[18px] font-semibold text-[#1c1c1e] tracking-tight mb-1">
              {s.name}
            </div>
            <div className="text-[11px] font-mono font-medium text-[#86868b] tracking-[1px] uppercase mb-4">
              {s.short}
            </div>
            <div className="text-[13px] text-[#48484a] leading-relaxed">
              {s.text}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
