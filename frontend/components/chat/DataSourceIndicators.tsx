"use client";

interface DataSource {
  id: string;
  label: string;
  icon: React.ReactNode;
  active: boolean;
}

interface DataSourceIndicatorsProps {
  sources: DataSource[];
}

export default function DataSourceIndicators({
  sources,
}: DataSourceIndicatorsProps) {
  if (sources.length === 0) return null;

  return (
    <div className="flex items-center justify-center gap-4 py-1.5 opacity-50 hover:opacity-80 transition-opacity">
      {sources.map((src) => (
        <div key={src.id} className="flex items-center gap-1.5">
          <div className="w-4 h-4 text-[#86868b]">{src.icon}</div>
          <span className="text-[10px] text-[#86868b] font-ui tracking-wide uppercase">
            {src.label}
          </span>
          <div className="relative w-1.5 h-1.5">
            <div
              className={`absolute inset-0 rounded-full ${
                src.active ? "bg-green-500" : "bg-[#c8c8cc]"
              }`}
            />
            {src.active && (
              <div className="absolute inset-0 rounded-full bg-green-500 animate-ping opacity-75" />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
