import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  INITIAL_ACTIVITIES,
  INITIAL_INVOICES,
  INITIAL_NOTIFICATIONS,
  INITIAL_SETTINGS,
  INITIAL_SUPPLIERS,
} from '../data/mockData';
import {
  clearAllDemoStorage,
  loadStoredInvoices,
  loadStoredSettings,
  saveStoredInvoices,
  saveStoredSettings,
} from '../services/storageService';
import type {
  ActivityEvent,
  AppRoute,
  Invoice,
  InvoiceStatus,
  NotificationItem,
  Supplier,
  WorkspaceSettings,
} from '../types/domain';

interface WorkspaceContextValue {
  activeRoute: AppRoute;
  navigate: (
    route: AppRoute,
    options?: { invoiceId?: string; supplierFilterId?: string }
  ) => void;
  invoices: Invoice[];
  suppliers: Supplier[];
  activities: ActivityEvent[];
  notifications: NotificationItem[];
  settings: WorkspaceSettings;
  selectedInvoiceId: string;
  selectInvoiceForReview: (invoiceId: string) => void;
  supplierFilterId: string | null;
  clearSupplierFilter: () => void;
  addUploadedInvoice: (invoice: Invoice) => void;
  updateInvoice: (updatedInvoice: Invoice, actionSummary?: string) => void;
  updateInvoiceStatus: (
    invoiceId: string,
    status: InvoiceStatus,
    reason?: string
  ) => void;
  updateSettings: (nextSettings: WorkspaceSettings) => void;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
  resetDemoWorkspace: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

function formatNowLabel(): string {
  return new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [activeRoute, setActiveRoute] = useState<AppRoute>('dashboard');
  const [invoices, setInvoices] = useState<Invoice[]>(
    () => loadStoredInvoices() ?? INITIAL_INVOICES
  );
  const [suppliers] = useState<Supplier[]>(INITIAL_SUPPLIERS);
  const [activities, setActivities] = useState<ActivityEvent[]>(INITIAL_ACTIVITIES);
  const [notifications, setNotifications] =
    useState<NotificationItem[]>(INITIAL_NOTIFICATIONS);
  const [settings, setSettings] = useState<WorkspaceSettings>(
    () => loadStoredSettings() ?? INITIAL_SETTINGS
  );
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string>(
    () => (loadStoredInvoices() ?? INITIAL_INVOICES)[0]?.id ?? 'inv-1041'
  );
  const [supplierFilterId, setSupplierFilterId] = useState<string | null>(null);

  useEffect(() => {
    saveStoredInvoices(invoices);
  }, [invoices]);

  useEffect(() => {
    saveStoredSettings(settings);
  }, [settings]);

  const navigate = useCallback(
    (
      route: AppRoute,
      options?: { invoiceId?: string; supplierFilterId?: string }
    ) => {
      if (options?.invoiceId) {
        setSelectedInvoiceId(options.invoiceId);
      }
      if (options?.supplierFilterId !== undefined) {
        setSupplierFilterId(options.supplierFilterId || null);
      } else if (route !== 'invoices') {
        setSupplierFilterId(null);
      }
      setActiveRoute(route);
    },
    []
  );

  const selectInvoiceForReview = useCallback((invoiceId: string) => {
    setSelectedInvoiceId(invoiceId);
    setActiveRoute('review');
  }, []);

  const clearSupplierFilter = useCallback(() => {
    setSupplierFilterId(null);
  }, []);

  const appendActivity = useCallback(
    (event: Omit<ActivityEvent, 'id' | 'timestamp'>) => {
      const entry: ActivityEvent = {
        id: `act-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        timestamp: `Today, ${formatNowLabel()}`,
        ...event,
      };
      setActivities((prev) => [entry, ...prev].slice(0, 12));
    },
    []
  );

  const addUploadedInvoice = useCallback(
    (invoice: Invoice) => {
      setInvoices((prev) => [invoice, ...prev]);
      setSelectedInvoiceId(invoice.id);
      appendActivity({
        actor: 'CA Ananya Deshmukh',
        action: `Staged local file "${invoice.documentFileName}" into Pending Review`,
        invoiceId: invoice.id,
        invoiceNumber: invoice.invoiceNumber,
        tone: 'neutral',
      });
    },
    [appendActivity]
  );

  const updateInvoice = useCallback(
    (updatedInvoice: Invoice, actionSummary?: string) => {
      setInvoices((prev) =>
        prev.map((inv) => (inv.id === updatedInvoice.id ? updatedInvoice : inv))
      );
      const tone: ActivityEvent['tone'] =
        updatedInvoice.status === 'Verified'
          ? 'success'
          : updatedInvoice.status === 'Flagged'
            ? 'warning'
            : 'neutral';

      appendActivity({
        actor: 'CA Ananya Deshmukh',
        action: actionSummary ?? 'Saved review changes to invoice fields',
        invoiceId: updatedInvoice.id,
        invoiceNumber: updatedInvoice.invoiceNumber,
        tone,
      });
    },
    [appendActivity]
  );

  const updateInvoiceStatus = useCallback(
    (invoiceId: string, status: InvoiceStatus, reason?: string) => {
      let targetNumber = '';
      setInvoices((prev) =>
        prev.map((inv) => {
          if (inv.id !== invoiceId) return inv;
          targetNumber = inv.invoiceNumber;
          return {
            ...inv,
            status,
            flagReason: status === 'Flagged' ? reason || inv.flagReason : undefined,
          };
        })
      );

      if (targetNumber) {
        appendActivity({
          actor: 'CA Ananya Deshmukh',
          action:
            status === 'Verified'
              ? 'Verified and approved invoice record'
              : status === 'Flagged'
                ? `Flagged invoice for review${reason ? `: ${reason}` : ''}`
                : 'Returned invoice to Pending Review',
          invoiceId,
          invoiceNumber: targetNumber,
          tone:
            status === 'Verified'
              ? 'success'
              : status === 'Flagged'
                ? 'warning'
                : 'neutral',
        });
      }
    },
    [appendActivity]
  );

  const updateSettings = useCallback((nextSettings: WorkspaceSettings) => {
    setSettings({ ...nextSettings, requireHumanReview: true });
  }, []);

  const markNotificationRead = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((item) => (item.id === id ? { ...item, read: true } : item))
    );
  }, []);

  const markAllNotificationsRead = useCallback(() => {
    setNotifications((prev) => prev.map((item) => ({ ...item, read: true })));
  }, []);

  const resetDemoWorkspace = useCallback(() => {
    clearAllDemoStorage();
    setInvoices(INITIAL_INVOICES);
    setSettings(INITIAL_SETTINGS);
    setActivities(INITIAL_ACTIVITIES);
    setNotifications(INITIAL_NOTIFICATIONS);
    setSelectedInvoiceId(INITIAL_INVOICES[0].id);
    setSupplierFilterId(null);
  }, []);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      activeRoute,
      navigate,
      invoices,
      suppliers,
      activities,
      notifications,
      settings,
      selectedInvoiceId,
      selectInvoiceForReview,
      supplierFilterId,
      clearSupplierFilter,
      addUploadedInvoice,
      updateInvoice,
      updateInvoiceStatus,
      updateSettings,
      markNotificationRead,
      markAllNotificationsRead,
      resetDemoWorkspace,
    }),
    [
      activeRoute,
      navigate,
      invoices,
      suppliers,
      activities,
      notifications,
      settings,
      selectedInvoiceId,
      selectInvoiceForReview,
      supplierFilterId,
      clearSupplierFilter,
      addUploadedInvoice,
      updateInvoice,
      updateInvoiceStatus,
      updateSettings,
      markNotificationRead,
      markAllNotificationsRead,
      resetDemoWorkspace,
    ]
  );

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return ctx;
}
