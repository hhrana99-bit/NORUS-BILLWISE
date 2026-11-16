import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
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
  detectDuplicateWarning,
  removeLocalStagedInvoice,
} from '../services/invoiceService';
import {
  isBlobObjectUrl,
  revokeAllBlobUrls,
  revokeUnusedBlobUrls,
} from '../services/objectUrlService';
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

export type PendingNavigation =
  | {
      type: 'route';
      route: AppRoute;
      options?: { invoiceId?: string; supplierFilterId?: string };
    }
  | {
      type: 'invoice';
      invoiceId: string;
    };

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
  hasUnsavedReviewChanges: boolean;
  setHasUnsavedReviewChanges: (dirty: boolean) => void;
  pendingNavigation: PendingNavigation | null;
  cancelPendingNavigation: () => void;
  commitPendingNavigation: () => void;
  supplierFilterId: string | null;
  clearSupplierFilter: () => void;
  addUploadedInvoice: (invoice: Invoice) => void;
  deleteLocalInvoice: (invoiceId: string) => boolean;
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

export function filterNotificationsBySettings(
  items: NotificationItem[],
  settings: Pick<
    WorkspaceSettings,
    'notifyFlaggedInvoices' | 'notifyDuplicateAlerts' | 'notifyDailyDigest'
  >
): NotificationItem[] {
  return items.filter((item) => {
    if (item.category === 'flagged') return settings.notifyFlaggedInvoices;
    if (item.category === 'duplicate') return settings.notifyDuplicateAlerts;
    if (item.category === 'digest') return settings.notifyDailyDigest;
    return true;
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
  const [hasUnsavedReviewChanges, setHasUnsavedReviewChanges] = useState(false);
  const [pendingNavigation, setPendingNavigation] =
    useState<PendingNavigation | null>(null);

  const invoicesRef = useRef<Invoice[]>(invoices);
  const createdBlobUrlsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    invoicesRef.current = invoices;
    saveStoredInvoices(invoices);
  }, [invoices]);

  useEffect(() => {
    saveStoredSettings(settings);
  }, [settings]);

  useEffect(() => {
    const trackedUrls = createdBlobUrlsRef.current;
    return () => {
      for (const url of trackedUrls) {
        if (typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
          URL.revokeObjectURL(url);
        }
      }
      trackedUrls.clear();
    };
  }, []);

  const performRouteNavigation = useCallback(
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

  const navigate = useCallback(
    (
      route: AppRoute,
      options?: { invoiceId?: string; supplierFilterId?: string }
    ) => {
      const wouldLeaveReview = activeRoute === 'review' && route !== 'review';
      const wouldSwitchInvoice =
        activeRoute === 'review' &&
        route === 'review' &&
        Boolean(options?.invoiceId && options.invoiceId !== selectedInvoiceId);

      if (hasUnsavedReviewChanges && (wouldLeaveReview || wouldSwitchInvoice)) {
        setPendingNavigation({ type: 'route', route, options });
        return;
      }

      performRouteNavigation(route, options);
    },
    [activeRoute, hasUnsavedReviewChanges, performRouteNavigation, selectedInvoiceId]
  );

  const selectInvoiceForReview = useCallback(
    (invoiceId: string) => {
      const wouldSwitchInvoice =
        activeRoute === 'review' && invoiceId !== selectedInvoiceId;

      if (hasUnsavedReviewChanges && wouldSwitchInvoice) {
        setPendingNavigation({ type: 'invoice', invoiceId });
        return;
      }

      setSelectedInvoiceId(invoiceId);
      setActiveRoute('review');
    },
    [activeRoute, hasUnsavedReviewChanges, selectedInvoiceId]
  );

  const cancelPendingNavigation = useCallback(() => {
    setPendingNavigation(null);
  }, []);

  const commitPendingNavigation = useCallback(() => {
    const target = pendingNavigation;
    setPendingNavigation(null);
    setHasUnsavedReviewChanges(false);
    if (!target) return;

    if (target.type === 'invoice') {
      setSelectedInvoiceId(target.invoiceId);
      setActiveRoute('review');
    } else {
      performRouteNavigation(target.route, target.options);
    }
  }, [pendingNavigation, performRouteNavigation]);

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

  const appendNotification = useCallback(
    (item: Omit<NotificationItem, 'id' | 'timeLabel' | 'read'>) => {
      const entry: NotificationItem = {
        id: `notif-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        timeLabel: 'Just now',
        read: false,
        ...item,
      };
      setNotifications((prev) => [entry, ...prev].slice(0, 12));
    },
    []
  );

  const addUploadedInvoice = useCallback(
    (invoice: Invoice) => {
      if (isBlobObjectUrl(invoice.localPreviewUrl)) {
        createdBlobUrlsRef.current.add(invoice.localPreviewUrl);
      }

      const dupWarning = settings.enableDuplicateWarnings
        ? detectDuplicateWarning(invoice, invoicesRef.current)
        : undefined;
      const stagedInvoice: Invoice = dupWarning
        ? { ...invoice, duplicateWarning: dupWarning }
        : invoice;

      const next = [stagedInvoice, ...invoicesRef.current];
      invoicesRef.current = next;
      setInvoices(next);
      setSelectedInvoiceId(stagedInvoice.id);
      appendActivity({
        actor: 'CA Ananya Deshmukh',
        action: `Staged local file "${stagedInvoice.documentFileName}" into Pending Review`,
        invoiceId: stagedInvoice.id,
        invoiceNumber: stagedInvoice.invoiceNumber,
        tone: 'neutral',
      });

      if (dupWarning && settings.notifyDuplicateAlerts) {
        appendNotification({
          title: 'Potential duplicate staged',
          detail: `${stagedInvoice.invoiceNumber}: ${dupWarning}`,
          targetRoute: 'review',
          targetInvoiceId: stagedInvoice.id,
          category: 'duplicate',
        });
      }
    },
    [
      appendActivity,
      appendNotification,
      settings.enableDuplicateWarnings,
      settings.notifyDuplicateAlerts,
    ]
  );

  const deleteLocalInvoice = useCallback(
    (invoiceId: string): boolean => {
      const prev = invoicesRef.current;
      const { updated, removed } = removeLocalStagedInvoice(prev, invoiceId);
      if (!removed) return false;

      const revoked = revokeUnusedBlobUrls(prev, updated);
      for (const url of revoked) {
        createdBlobUrlsRef.current.delete(url);
      }

      invoicesRef.current = updated;
      setInvoices(updated);
      setNotifications((prevNotifs) =>
        prevNotifs.filter((n) => n.targetInvoiceId !== invoiceId)
      );

      if (selectedInvoiceId === invoiceId) {
        setHasUnsavedReviewChanges(false);
        setSelectedInvoiceId(updated[0]?.id ?? '');
      }
      if (
        pendingNavigation &&
        ((pendingNavigation.type === 'invoice' &&
          pendingNavigation.invoiceId === invoiceId) ||
          (pendingNavigation.type === 'route' &&
            pendingNavigation.options?.invoiceId === invoiceId))
      ) {
        setPendingNavigation(null);
      }

      appendActivity({
        actor: 'CA Ananya Deshmukh',
        action: `Removed locally staged demo invoice "${removed.documentFileName}" (local browser only)`,
        invoiceNumber: removed.invoiceNumber,
        tone: 'neutral',
      });

      return true;
    },
    [appendActivity, pendingNavigation, selectedInvoiceId]
  );

  const updateInvoice = useCallback(
    (updatedInvoice: Invoice, actionSummary?: string) => {
      const prevList = invoicesRef.current;
      const dupWarning = settings.enableDuplicateWarnings
        ? detectDuplicateWarning(updatedInvoice, prevList)
        : updatedInvoice.duplicateWarning;

      const finalInvoice: Invoice = {
        ...updatedInvoice,
        duplicateWarning: dupWarning,
      };

      if (isBlobObjectUrl(finalInvoice.localPreviewUrl)) {
        createdBlobUrlsRef.current.add(finalInvoice.localPreviewUrl);
      }

      const nextList = prevList.map((inv) =>
        inv.id === finalInvoice.id ? finalInvoice : inv
      );
      const revoked = revokeUnusedBlobUrls(prevList, nextList);
      for (const url of revoked) {
        createdBlobUrlsRef.current.delete(url);
      }

      invoicesRef.current = nextList;
      setInvoices(nextList);

      const tone: ActivityEvent['tone'] =
        finalInvoice.status === 'Verified'
          ? 'success'
          : finalInvoice.status === 'Flagged'
            ? 'warning'
            : 'neutral';

      appendActivity({
        actor: 'CA Ananya Deshmukh',
        action: actionSummary ?? 'Saved review changes to invoice fields',
        invoiceId: finalInvoice.id,
        invoiceNumber: finalInvoice.invoiceNumber,
        tone,
      });

      if (finalInvoice.status === 'Flagged' && settings.notifyFlaggedInvoices) {
        appendNotification({
          title: `Invoice flagged: ${finalInvoice.invoiceNumber}`,
          detail:
            finalInvoice.flagReason ??
            'Flagged in Review Centre for secondary verification.',
          targetRoute: 'review',
          targetInvoiceId: finalInvoice.id,
          category: 'flagged',
        });
      } else if (
        settings.enableDuplicateWarnings &&
        settings.notifyDuplicateAlerts &&
        dupWarning &&
        !updatedInvoice.duplicateWarning
      ) {
        appendNotification({
          title: `Duplicate warning: ${finalInvoice.invoiceNumber}`,
          detail: dupWarning,
          targetRoute: 'review',
          targetInvoiceId: finalInvoice.id,
          category: 'duplicate',
        });
      }
    },
    [
      appendActivity,
      appendNotification,
      settings.enableDuplicateWarnings,
      settings.notifyDuplicateAlerts,
      settings.notifyFlaggedInvoices,
    ]
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

        if (status === 'Flagged' && settings.notifyFlaggedInvoices) {
          appendNotification({
            title: `Invoice flagged: ${targetNumber}`,
            detail: reason ?? 'Flagged for secondary verification.',
            targetRoute: 'review',
            targetInvoiceId: invoiceId,
            category: 'flagged',
          });
        }
      }
    },
    [appendActivity, appendNotification, settings.notifyFlaggedInvoices]
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
    const revoked = revokeAllBlobUrls(invoicesRef.current);
    for (const url of revoked) {
      createdBlobUrlsRef.current.delete(url);
    }
    clearAllDemoStorage();
    invoicesRef.current = INITIAL_INVOICES;
    setInvoices(INITIAL_INVOICES);
    setSettings(INITIAL_SETTINGS);
    setActivities(INITIAL_ACTIVITIES);
    setNotifications(INITIAL_NOTIFICATIONS);
    setSelectedInvoiceId(INITIAL_INVOICES[0].id);
    setSupplierFilterId(null);
    setHasUnsavedReviewChanges(false);
    setPendingNavigation(null);
  }, []);

  const visibleNotifications = useMemo(
    () => filterNotificationsBySettings(notifications, settings),
    [notifications, settings]
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      activeRoute,
      navigate,
      invoices,
      suppliers,
      activities,
      notifications: visibleNotifications,
      settings,
      selectedInvoiceId,
      selectInvoiceForReview,
      hasUnsavedReviewChanges,
      setHasUnsavedReviewChanges,
      pendingNavigation,
      cancelPendingNavigation,
      commitPendingNavigation,
      supplierFilterId,
      clearSupplierFilter,
      addUploadedInvoice,
      deleteLocalInvoice,
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
      visibleNotifications,
      settings,
      selectedInvoiceId,
      selectInvoiceForReview,
      hasUnsavedReviewChanges,
      pendingNavigation,
      cancelPendingNavigation,
      commitPendingNavigation,
      supplierFilterId,
      clearSupplierFilter,
      addUploadedInvoice,
      deleteLocalInvoice,
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
