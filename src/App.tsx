import { AppShell } from './components/layout/AppShell';
import { DashboardPage } from './pages/DashboardPage';
import { InvoicesPage } from './pages/InvoicesPage';
import { ReportsPage } from './pages/ReportsPage';
import { ReviewCentrePage } from './pages/ReviewCentrePage';
import { SettingsPage } from './pages/SettingsPage';
import { SuppliersPage } from './pages/SuppliersPage';
import { WorkspaceProvider, useWorkspace } from './state/WorkspaceContext';

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
        <WorkspaceRouter />
      </AppShell>
    </WorkspaceProvider>
  );
}
