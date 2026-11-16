import { lazy, Suspense } from 'react';
import { AppShell } from './components/layout/AppShell';
import { WorkspaceProvider, useWorkspace } from './state/WorkspaceContext';

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const InvoicesPage = lazy(() =>
  import('./pages/InvoicesPage').then((m) => ({ default: m.InvoicesPage }))
);
const ReviewCentrePage = lazy(() =>
  import('./pages/ReviewCentrePage').then((m) => ({ default: m.ReviewCentrePage }))
);
const SuppliersPage = lazy(() =>
  import('./pages/SuppliersPage').then((m) => ({ default: m.SuppliersPage }))
);
const ReportsPage = lazy(() =>
  import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage }))
);
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);

function RouteLoadingFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-6"
    >
      <div className="h-5 w-48 animate-pulse rounded bg-slate-200" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
      </div>
      <span className="sr-only">Loading workspace view...</span>
    </div>
  );
}

function WorkspaceRouter() {
  const { activeRoute } = useWorkspace();

  switch (activeRoute) {
    case 'dashboard':
      return <DashboardPage />;
    case 'invoices':
      return <InvoicesPage />;
    case 'review':
      return <ReviewCentrePage />;
    case 'suppliers':
      return <SuppliersPage />;
    case 'reports':
      return <ReportsPage />;
    case 'settings':
      return <SettingsPage />;
    default:
      return <DashboardPage />;
  }
}

export default function App() {
  return (
    <WorkspaceProvider>
      <AppShell>
        <Suspense fallback={<RouteLoadingFallback />}>
          <WorkspaceRouter />
        </Suspense>
      </AppShell>
    </WorkspaceProvider>
  );
}
