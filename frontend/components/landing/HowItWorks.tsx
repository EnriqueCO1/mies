const steps = [
  {
    num: "01",
    title: "Introduces los datos del proyecto",
    text: (
      <>
        Dirección, <span className="text-[#1c1c1e]">municipio</span>,{" "}
        <span className="text-[#1c1c1e]">referencia catastral</span> y, si la
        hay, la ordenanza específica. Nada más. El asistente se configura
        automáticamente.
      </>
    ),
  },
  {
    num: "02",
    title: "Mies carga el Catastro por ti",
    text: (
      <>
        Con la referencia catastral, consulta los servicios{" "}
        <span className="text-[#1c1c1e]">INSPIRE WFS</span> del Catastro en
        paralelo y extrae superficie construida, superficie del solar, año,
        uso, plantas y dirección normalizada de la vivienda.
      </>
    ),
  },
  {
    num: "03",
    title: "Pregunta. El sistema cruza todas las fuentes.",
    text: (
      <>
        Cada consulta busca en el{" "}
        <span className="text-[#1c1c1e]">
          PGOU de tu municipio
        </span>
        , en todo el <span className="text-[#1c1c1e]">CTE</span>, en la{" "}
        <span className="text-[#1c1c1e]">LOE</span> y — cuando pides precios
        o mediciones — en la{" "}
        <span className="text-[#1c1c1e]">BCCA</span>. Cada dato viene citado
        a su fuente (documento, artículo, página).
      </>
    ),
  },
  {
    num: "04",
    title: "Exporta el documento listo para visado",
    text: (
      <>
        Memoria descriptiva, anejos de cumplimiento del CTE, pliegos,
        mediciones. Generados en{" "}
        <span className="text-[#1c1c1e]">DOCX</span> con las fuentes ya
        incorporadas — listos para firma y visado.
      </>
    ),
  },
];

export default function HowItWorks() {
  return (
    <section
      className="max-w-[1200px] mx-auto py-36 px-12 max-md:py-20 max-md:px-6"
      id="how"
    >
      <div className="font-mono text-[11px] font-medium text-[#86868b] tracking-[2px] uppercase mb-5">
        Cómo funciona
      </div>
      <h2 className="text-[clamp(32px,4vw,48px)] font-semibold text-[#1c1c1e] tracking-[-1.5px] leading-tight mb-5">
        De la referencia catastral
        <br />
        al DOCX visado.
      </h2>
      <p className="text-[18px] text-[#48484a] leading-relaxed max-w-[640px] mb-18">
        Diseñado específicamente para el{" "}
        <span className="text-[#1c1c1e] font-medium">
          proyecto de ejecución
        </span>
        . Cruza el PGOU del municipio con el CTE, la LOE, el BCCA y los
        datos del Catastro para que cada decisión del proyecto se apoye en
        normativa vigente y verificable.
      </p>

      {/* 4 steps — 2×2 on tablet, horizontal on desktop, stacked on mobile. */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12 max-md:gap-10 mt-18">
        {steps.map((step, i) => (
          <div key={i} className="flex-1 relative">
            <div className="font-mono text-[64px] font-bold text-black/[0.05] tracking-[-3px] leading-none mb-5">
              {step.num}
            </div>
            <div className="text-[20px] font-semibold text-[#1c1c1e] tracking-tight mb-3">
              {step.title}
            </div>
            <div className="text-[15px] text-[#48484a] leading-relaxed">
              {step.text}
            </div>
            {i < steps.length - 1 && (
              <div className="absolute top-10 -right-6 w-4 h-px bg-[#86868b] max-lg:hidden" />
            )}
          </div>
        ))}
      </div>

      {/* Compliance / result statement — ties the flow to its purpose. */}
      <div className="mt-28 max-md:mt-20 border-t border-black/[0.06] pt-12">
        <div className="grid grid-cols-1 lg:grid-cols-[2fr_3fr] gap-12 items-start">
          <div>
            <div className="font-mono text-[11px] font-medium text-[#86868b] tracking-[2px] uppercase mb-4">
              Por qué importa
            </div>
            <h3 className="text-[clamp(24px,3vw,34px)] font-semibold text-[#1c1c1e] tracking-[-0.8px] leading-tight">
              Normativa vigente,
              <br />
              citada en cada respuesta.
            </h3>
          </div>
          <div className="space-y-5 text-[15px] text-[#48484a] leading-relaxed">
            <p>
              Un proyecto de ejecución que no cumpla el CTE, el PGOU o la
              LOE no se visa. Mies no te deja improvisar: cada exigencia
              técnica se cruza contra la normativa indexada y cada dato de
              la vivienda contra el Catastro. Si el PGOU del municipio del
              proyecto no está en nuestro índice, el asistente lo dice en
              vez de inventar ordenanzas.
            </p>
            <p>
              Los precios para mediciones y presupuestos salen de la{" "}
              <span className="text-[#1c1c1e]">
                Base de Coste de la Construcción de Andalucía
              </span>
              , no de estimaciones. Los documentos generados llevan la
              referencia normativa integrada, listos para el visado del
              colegio profesional sin correcciones.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
