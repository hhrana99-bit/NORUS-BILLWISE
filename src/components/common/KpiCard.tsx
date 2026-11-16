import type { ReactNode } from 'react';

export function KpiCard({
  label,
  value,
  sublabel,
  icon,
  tone = 'slate',
  onClick,
}: {
  label: string;
  value: string | number;
  sublabel: string;
  icon: ReactNode;
  tone?: 'slate' | 'amber' | 'emerald' | 'rose';
  onClick?: () => void;
}) {
  const iconTone: Record<typeof tone, string> = {
    slate: 'bg-slate-100 text-slate-700',
    amber: 'bg-amber-50 text-amber-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    rose: 'bg-rose-50 text-rose-700',
  };

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="w-full rounded-xl border border-slate-200 bg-white p-5 text-left transition-colors duration-150 hover:border-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-slate-500">{label}</p>
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 font-mono tabular-nums">
              {value}
            </p>
          </div>
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconTone[tone]}`}
          >
            {icon}
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500 tabular-nums">{sublabel}</p>
      </button>
    );
  }

  return (
    <div className="w-full rounded-xl border border-slate-200 bg-white p-5 text-left">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-slate-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 font-mono tabular-nums">
            {value}
          </p>
        </div>
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${iconTone[tone]}`}
        >
          {icon}
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-500 tabular-nums">{sublabel}</p>
    </div>
  );
}
