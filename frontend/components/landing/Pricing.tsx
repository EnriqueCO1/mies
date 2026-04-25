const plans = [
  {
    name: "Gratis",
    desc: "Prueba el asistente",
    amount: "0 €",
    period: "para siempre",
    features: ["10 consultas al día", "1 proyecto activo", "Historial 7 días"],
    featured: false,
  },
  {
    name: "Profesional",
    desc: "Para arquitectos en activo",
    amount: "19 €",
    period: "al mes",
    features: [
      "Consultas ilimitadas",
      "Proyectos ilimitados",
      "Historial completo",
      "Generación de documentos",
    ],
    featured: true,
    badge: "Recomendado",
  },
  {
    name: "Estudio",
    desc: "Para estudios de arquitectura",
    amount: "12 €",
    period: "por usuario / mes",
    features: [
      "Todo en Profesional",
      "Panel de administración",
      "Informes de uso",
      "Soporte prioritario",
    ],
    featured: false,
  },
];

export default function Pricing() {
  return (
    <section className="max-w-[1200px] mx-auto py-36 px-12 max-md:py-20 max-md:px-6" id="pricing">
      <div className="font-mono text-[11px] font-medium text-[#86868b] tracking-[2px] uppercase mb-5">
        Precios
      </div>
      <h2 className="text-[clamp(32px,4vw,48px)] font-semibold text-[#1c1c1e] tracking-[-1.5px] leading-tight mb-5">
        Simple y transparente.
      </h2>
      <p className="text-[18px] text-[#48484a] leading-relaxed max-w-[600px] mb-18">
        Sin sorpresas. Sin permanencia. Cancela cuando quieras.
      </p>

      <div className="grid grid-cols-3 gap-px max-md:grid-cols-1 mt-18">
        {plans.map((plan, i) => (
          <div
            key={i}
            className={`p-13 max-md:p-8 flex flex-col transition-colors hover:bg-[#e8e8ed]
              ${plan.featured
                ? "bg-[#e8e8ed] border border-black/[0.08] -my-2 -mx-px z-10 max-md:my-0 max-md:mx-0"
                : "bg-[#f5f5f7]"
              }
            `}
          >
            {plan.badge && (
              <div className="font-mono text-[10px] font-medium tracking-[1.5px] uppercase text-white bg-[#1c1c1e] px-3.5 py-1.5 rounded-none w-fit mb-6">
                {plan.badge}
              </div>
            )}
            <div className="text-[22px] font-semibold text-[#1c1c1e] tracking-tight mb-2">
              {plan.name}
            </div>
            <div className="text-[14px] text-[#48484a] mb-8">
              {plan.desc}
            </div>
            <div className="text-[48px] font-bold text-[#1c1c1e] tracking-[-2px] mb-1">
              {plan.amount}
            </div>
            <div className="text-[14px] text-[#86868b] mb-9">
              {plan.period}
            </div>
            <ul className="flex flex-col gap-3.5 mt-auto">
              {plan.features.map((feat, j) => (
                <li
                  key={j}
                  className="text-[14px] text-[#48484a] pl-5 relative before:content-['—'] before:absolute before:left-0 before:text-[#86868b]"
                >
                  {feat}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}
