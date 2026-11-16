export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 select-none">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white ring-1 ring-indigo-400/30">
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M6 3h9l4 4v14H6z" />
          <path d="M15 3v4h4" />
          <path d="M9 12l2 2 4-4" />
          <path d="M9 17h6" />
        </svg>
      </div>
      {!compact && (
        <div className="min-w-0">
          <span className="block text-sm font-semibold tracking-tight text-white whitespace-nowrap">
            NORUS BILLWISE
          </span>
          <p className="text-[11px] font-medium tracking-wide text-slate-400 whitespace-nowrap">
            Beyond the World.
          </p>
        </div>
      )}
    </div>
  );
}
