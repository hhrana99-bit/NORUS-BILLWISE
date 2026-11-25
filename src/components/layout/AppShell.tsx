import { Info } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useWorkspace } from '../../state/WorkspaceContext';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { isDemoMode } = useWorkspace();

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      <Sidebar
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMobileNav={() => setMobileOpen(true)} />
        {isDemoMode && (
          <div
            role="status"
            aria-label="Demo mode notice"
            className="border-b border-amber-300 bg-amber-50 px-4 py-2.5 text-xs text-amber-950 sm:px-6 lg:px-7"
          >
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-start gap-2 sm:items-center">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 sm:mt-0" />
                <p className="min-w-0 leading-snug">
                  <strong className="font-mono tracking-wide text-amber-950">
                    DEMO MODE — SAMPLE DATA:
                  </strong>{' '}
                  Sign-in is temporarily bypassed for read-only preview with
                  synthetic fixtures. Uploads, edits, verification, flagging,
                  resolving, reopening, deletion, and server exports are disabled.
                </p>
              </div>
              <span className="shrink-0 rounded border border-amber-300 bg-white px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-900">
                READ-ONLY SAMPLE
              </span>
            </div>
          </div>
        )}
        <main className="flex-1 p-4 sm:p-6 lg:p-7">
          <div className="mx-auto max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

