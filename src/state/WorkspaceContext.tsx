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
  apiClient,
  formatApiErrorMessage,
  type FlagInvoicePayload,
  type InvoiceCreatePayload,
  type RegisterApiPayload,
  type ResolveFlagPayload,
  type SupplierCreatePayload,
  type SupplierUpdatePayload,
  type VerifyInvoicePayload,
  type WorkspaceSettingsUpdatePayload,
} from '../services/apiClient';
import {
  buildInvoiceUpdatePayload,
  mapAuditEventToActivity,
  mapInvoiceDetailDto,
  mapInvoiceSummaryDto,
  mapMonthlyTrendDto,
  mapSupplierSummaryDto,
  mapWorkspaceSettingsDto,
} from '../services/apiMappers';
import type {
  ActivityEvent,
  ApiAuditEvent,
  ApiReportExceptionItem,
  ApiReportSummary,
  ApiReviewHistory,
  AppRoute,
  AuthenticatedUser,
  HistoricalMonthStat,
  Invoice,
  LocalUiPreferences,
  NotificationItem,
  OrganizationSummary,
  SupplierSummary,
  WorkspaceMembershipSummary,
  WorkspaceRole,
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
    }
  | {
      type: 'workspace';
      workspaceId: string;
    };

export type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated';

const SESSION_ACTIVE_WORKSPACE_KEY = 'norus_billwise_active_workspace_id';
const LOCAL_UI_PREFS_KEY = 'norus_billwise_ui_prefs_v1';

const DEFAULT_SETTINGS_PLACEHOLDER: WorkspaceSettings = {
  workspaceName: 'Workspace',
  firmType: 'Chartered Accountancy Practice',
  workspaceCode: '',
  legalEntityName: '',
  companyGstin: '',
  companyPan: '',
  registeredAddress: '',
  requireHumanReview: true,
  enableDuplicateWarnings: true,
  autoFlagTaxMismatch: true,
  currency: 'INR',
  financialYear: 'April - March',
  dateFormat: 'DD/MM/YYYY',
  taxRegime: 'India GST (CGST / SGST / IGST)',
  notifyFlaggedInvoices: true,
  notifyDailyDigest: false,
  notifyDuplicateAlerts: true,
  roundingTolerance: 1,
  defaultCurrency: 'INR',
};

const DEFAULT_LOCAL_UI_PREFS: LocalUiPreferences = {
  compactTables: false,
};

export function isLatestRequestSeq(
  currentSeq: number,
  requestSeq: number
): boolean {
  return currentSeq === requestSeq;
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

function readStoredWorkspaceId(): string | null {
  try {
    if (typeof sessionStorage === 'undefined') return null;
    return sessionStorage.getItem(SESSION_ACTIVE_WORKSPACE_KEY);
  } catch {
    return null;
  }
}

function writeStoredWorkspaceId(workspaceId: string | null): void {
  try {
    if (typeof sessionStorage === 'undefined') return;
    if (workspaceId) {
      sessionStorage.setItem(SESSION_ACTIVE_WORKSPACE_KEY, workspaceId);
    } else {
      sessionStorage.removeItem(SESSION_ACTIVE_WORKSPACE_KEY);
    }
  } catch {
    // Ignore storage access errors in restricted environments
  }
}

function loadLocalUiPrefs(): LocalUiPreferences {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_LOCAL_UI_PREFS;
    const raw = localStorage.getItem(LOCAL_UI_PREFS_KEY);
    if (!raw) return DEFAULT_LOCAL_UI_PREFS;
    const parsed = JSON.parse(raw) as Partial<LocalUiPreferences>;
    return {
      compactTables: Boolean(parsed?.compactTables),
    };
  } catch {
    return DEFAULT_LOCAL_UI_PREFS;
  }
}

function saveLocalUiPrefs(prefs: LocalUiPreferences): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(LOCAL_UI_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore storage quota errors
  }
}

function pickActiveWorkspaceId(
  memberships: WorkspaceMembershipSummary[],
  preferredId: string | null
): string | null {
  if (memberships.length === 0) return null;
  if (preferredId && memberships.some((m) => m.workspaceId === preferredId)) {
    return preferredId;
  }
  return memberships[0].workspaceId;
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

interface WorkspaceContextValue {
  authStatus: AuthStatus;
  currentUser: AuthenticatedUser | null;
  organizations: OrganizationSummary[];
  workspaces: WorkspaceMembershipSummary[];
  activeWorkspaceId: string | null;
  activeWorkspace: WorkspaceMembershipSummary | null;
  activeWorkspaceRole: WorkspaceRole | null;
  sessionExpiredMessage: string | null;
  clearSessionExpiredMessage: () => void;

  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterApiPayload) => Promise<void>;
  logout: () => Promise<void>;
  switchWorkspace: (workspaceId: string) => void;

  activeRoute: AppRoute;
  navigate: (
    route: AppRoute,
    options?: { invoiceId?: string; supplierFilterId?: string }
  ) => void;

  invoices: Invoice[];
  invoicesTotal: number;
  suppliers: SupplierSummary[];
  activities: ActivityEvent[];
  auditEvents: ApiAuditEvent[];
  auditEventsTotal: number;
  reportSummary: ApiReportSummary | null;
  monthlyTrend: HistoricalMonthStat[];
  monthlyTrendMeta: {
    window: '6m' | '12m' | 'all';
    excludedCount: number;
    outOfWindowCount: number;
    currency: string;
  };
  reportExceptions: ApiReportExceptionItem[];
  reportExceptionsTotal: number;
  notifications: NotificationItem[];
  settings: WorkspaceSettings;
  localUiPrefs: LocalUiPreferences;
  updateLocalUiPrefs: (prefs: LocalUiPreferences) => void;

  workspaceLoading: boolean;
  workspaceError: string | null;
  reportsError: string | null;
  mutationInFlight: boolean;

  selectedInvoiceId: string;
  selectedInvoiceDetail: Invoice | null;
  selectedReviewHistory: ApiReviewHistory | null;
  detailLoading: boolean;
  detailError: string | null;
  selectInvoiceForReview: (invoiceId: string) => void;
  refreshSelectedInvoiceDetail: (invoiceId?: string) => Promise<void>;

  hasUnsavedReviewChanges: boolean;
  setHasUnsavedReviewChanges: (dirty: boolean) => void;
  pendingNavigation: PendingNavigation | null;
  cancelPendingNavigation: () => void;
  commitPendingNavigation: () => void;
  supplierFilterId: string | null;
  clearSupplierFilter: () => void;

  refreshWorkspace: () => Promise<void>;
  loadTrendWindow: (window: '6m' | '12m' | 'all') => Promise<void>;
  uploadInvoiceFile: (params: {
    file: File;
    supplierName?: string;
    invoiceNumber?: string;
  }) => Promise<{ documentId: string; invoiceId: string | null }>;
  createManualInvoice: (payload: InvoiceCreatePayload) => Promise<Invoice>;
  saveInvoiceChanges: (original: Invoice, draft: Invoice) => Promise<Invoice>;
  verifyInvoiceAction: (
    invoiceId: string,
    payload: VerifyInvoicePayload
  ) => Promise<Invoice>;
  flagInvoiceAction: (
    invoiceId: string,
    payload: FlagInvoicePayload
  ) => Promise<Invoice>;
  resolveFlagAction: (
    flagId: string,
    payload: ResolveFlagPayload
  ) => Promise<void>;
  reopenInvoiceAction: (invoiceId: string, reason: string) => Promise<Invoice>;
  deleteInvoiceAction: (
    invoiceId: string,
    deletionReason?: string
  ) => Promise<void>;
  createSupplierAction: (
    payload: SupplierCreatePayload
  ) => Promise<SupplierSummary>;
  updateSupplierAction: (
    supplierId: string,
    payload: SupplierUpdatePayload
  ) => Promise<SupplierSummary>;
  updateSettingsAction: (
    payload: WorkspaceSettingsUpdatePayload
  ) => Promise<WorkspaceSettings>;
  exportCsvReport: (params?: {
    status?: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
    dateFrom?: string;
    dateTo?: string;
    currency?: string;
  }) => Promise<string>;

  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(
  undefined
);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking');
  const [currentUser, setCurrentUser] = useState<AuthenticatedUser | null>(
    null
  );
  const [organizations, setOrganizations] = useState<OrganizationSummary[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceMembershipSummary[]>(
    []
  );
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(
    () => readStoredWorkspaceId()
  );
  const [sessionExpiredMessage, setSessionExpiredMessage] = useState<
    string | null
  >(null);

  const [activeRoute, setActiveRoute] = useState<AppRoute>('dashboard');
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesTotal, setInvoicesTotal] = useState<number>(0);
  const [suppliers, setSuppliers] = useState<SupplierSummary[]>([]);
  const [auditEvents, setAuditEvents] = useState<ApiAuditEvent[]>([]);
  const [auditEventsTotal, setAuditEventsTotal] = useState<number>(0);
  const [reportSummary, setReportSummary] = useState<ApiReportSummary | null>(
    null
  );
  const [monthlyTrend, setMonthlyTrend] = useState<HistoricalMonthStat[]>([]);
  const [monthlyTrendMeta, setMonthlyTrendMeta] = useState<{
    window: '6m' | '12m' | 'all';
    excludedCount: number;
    outOfWindowCount: number;
    currency: string;
  }>({
    window: '6m',
    excludedCount: 0,
    outOfWindowCount: 0,
    currency: 'INR',
  });
  const [reportExceptions, setReportExceptions] = useState<
    ApiReportExceptionItem[]
  >([]);
  const [reportExceptionsTotal, setReportExceptionsTotal] = useState<number>(0);
  const [settings, setSettings] = useState<WorkspaceSettings>(
    DEFAULT_SETTINGS_PLACEHOLDER
  );
  const [localUiPrefs, setLocalUiPrefs] = useState<LocalUiPreferences>(() =>
    loadLocalUiPrefs()
  );

  const [workspaceLoading, setWorkspaceLoading] = useState<boolean>(false);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [mutationInFlight, setMutationInFlight] = useState<boolean>(false);

  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string>('');
  const [selectedInvoiceDetail, setSelectedInvoiceDetail] =
    useState<Invoice | null>(null);
  const [selectedReviewHistory, setSelectedReviewHistory] =
    useState<ApiReviewHistory | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [supplierFilterId, setSupplierFilterId] = useState<string | null>(null);
  const [hasUnsavedReviewChanges, setHasUnsavedReviewChanges] = useState(false);
  const [pendingNavigation, setPendingNavigation] =
    useState<PendingNavigation | null>(null);
  const [readNotificationIds, setReadNotificationIds] = useState<Set<string>>(
    () => new Set()
  );

  const workspaceSeqRef = useRef<number>(0);
  const workspaceAbortRef = useRef<AbortController | null>(null);
  const detailSeqRef = useRef<number>(0);
  const detailAbortRef = useRef<AbortController | null>(null);
  const trendWindowRef = useRef<'6m' | '12m' | 'all'>('6m');
  const organizationsRef = useRef<OrganizationSummary[]>(organizations);

  useEffect(() => {
    organizationsRef.current = organizations;
  }, [organizations]);

  const resetWorkspaceData = useCallback(() => {
    workspaceAbortRef.current?.abort();
    detailAbortRef.current?.abort();
    workspaceSeqRef.current += 1;
    detailSeqRef.current += 1;

    setInvoices([]);
    setInvoicesTotal(0);
    setSuppliers([]);
    setAuditEvents([]);
    setAuditEventsTotal(0);
    setReportSummary(null);
    setMonthlyTrend([]);
    setMonthlyTrendMeta({
      window: trendWindowRef.current,
      excludedCount: 0,
      outOfWindowCount: 0,
      currency: 'INR',
    });
    setReportExceptions([]);
    setReportExceptionsTotal(0);
    setSettings(DEFAULT_SETTINGS_PLACEHOLDER);
    setWorkspaceError(null);
    setReportsError(null);
    setSelectedInvoiceId('');
    setSelectedInvoiceDetail(null);
    setSelectedReviewHistory(null);
    setDetailError(null);
    setSupplierFilterId(null);
    setHasUnsavedReviewChanges(false);
    setPendingNavigation(null);
    setReadNotificationIds(new Set());
  }, []);

  const clearSessionState = useCallback(
    (expiredMsg: string | null) => {
      resetWorkspaceData();
      setCurrentUser(null);
      setOrganizations([]);
      setWorkspaces([]);
      setActiveWorkspaceId(null);
      writeStoredWorkspaceId(null);
      setSessionExpiredMessage(expiredMsg);
      setAuthStatus('unauthenticated');
    },
    [resetWorkspaceData]
  );

  useEffect(() => {
    apiClient.setUnauthorizedHandler(() => {
      clearSessionState('Your session expired. Please sign in again.');
    });
    return () => {
      apiClient.setUnauthorizedHandler(null);
    };
  }, [clearSessionState]);

  const hydrateSession = useCallback(async () => {
    setAuthStatus('checking');
    try {
      const me = await apiClient.getMe();
      setCurrentUser(me.user);
      setOrganizations(me.organizations);
      setWorkspaces(me.workspaces);
      const chosenId = pickActiveWorkspaceId(
        me.workspaces,
        readStoredWorkspaceId()
      );
      setActiveWorkspaceId(chosenId);
      writeStoredWorkspaceId(chosenId);
      setSessionExpiredMessage(null);
      setAuthStatus('authenticated');
    } catch {
      clearSessionState(null);
    }
  }, [clearSessionState]);

  useEffect(() => {
    void hydrateSession();
  }, [hydrateSession]);

  const loadWorkspaceData = useCallback(
    async (
      workspaceId: string,
      options?: { trendWindow?: '6m' | '12m' | 'all' }
    ) => {
      workspaceAbortRef.current?.abort();
      const controller = new AbortController();
      workspaceAbortRef.current = controller;
      const reqSeq = ++workspaceSeqRef.current;

      const requestedWindow = options?.trendWindow ?? trendWindowRef.current;
      trendWindowRef.current = requestedWindow;

      setWorkspaceLoading(true);
      setWorkspaceError(null);
      setReportsError(null);

      try {
        const [
          detailRes,
          settingsRes,
          invoicesRes,
          suppliersRes,
          auditRes,
          summaryRes,
          trendRes,
          exceptionsRes,
        ] = await Promise.allSettled([
          apiClient.getWorkspaceDetail(workspaceId, controller.signal),
          apiClient.getWorkspaceSettings(workspaceId, controller.signal),
          apiClient.listInvoices(
            workspaceId,
            { page: 1, pageSize: 100, sortBy: 'invoiceDate', sortDir: 'desc' },
            controller.signal
          ),
          apiClient.listSuppliers(
            workspaceId,
            { page: 1, pageSize: 100 },
            controller.signal
          ),
          apiClient.listAuditEvents(
            workspaceId,
            { page: 1, pageSize: 50 },
            controller.signal
          ),
          apiClient.getReportSummary(workspaceId, undefined, controller.signal),
          apiClient.getMonthlyTrend(
            workspaceId,
            { window: requestedWindow },
            controller.signal
          ),
          apiClient.listReportExceptions(
            workspaceId,
            { page: 1, pageSize: 50 },
            controller.signal
          ),
        ]);

        if (
          controller.signal.aborted ||
          !isLatestRequestSeq(workspaceSeqRef.current, reqSeq)
        ) {
          return;
        }

        const primaryErrors: string[] = [];

        if (invoicesRes.status === 'fulfilled') {
          const mappedInvoices = invoicesRes.value.items.map(mapInvoiceSummaryDto);
          setInvoices(mappedInvoices);
          setInvoicesTotal(invoicesRes.value.total);
          setSelectedInvoiceId((prev) =>
            prev && mappedInvoices.some((inv) => inv.id === prev)
              ? prev
              : mappedInvoices[0]?.id ?? ''
          );
        } else if (!isAbortError(invoicesRes.reason)) {
          primaryErrors.push(formatApiErrorMessage(invoicesRes.reason));
        }

        if (suppliersRes.status === 'fulfilled') {
          setSuppliers(suppliersRes.value.items.map(mapSupplierSummaryDto));
        } else if (!isAbortError(suppliersRes.reason)) {
          primaryErrors.push(formatApiErrorMessage(suppliersRes.reason));
        }

        if (settingsRes.status === 'fulfilled') {
          const wsDetail =
            detailRes.status === 'fulfilled' ? detailRes.value : null;
          setSettings(
            mapWorkspaceSettingsDto(
              settingsRes.value,
              wsDetail,
              organizationsRef.current
            )
          );
        } else if (!isAbortError(settingsRes.reason)) {
          primaryErrors.push(formatApiErrorMessage(settingsRes.reason));
        }

        if (auditRes.status === 'fulfilled') {
          setAuditEvents(auditRes.value.items);
          setAuditEventsTotal(auditRes.value.total);
        }

        const repErrors: string[] = [];
        if (summaryRes.status === 'fulfilled') {
          setReportSummary(summaryRes.value);
        } else if (!isAbortError(summaryRes.reason)) {
          setReportSummary(null);
          repErrors.push(formatApiErrorMessage(summaryRes.reason));
        }

        if (trendRes.status === 'fulfilled') {
          setMonthlyTrend(mapMonthlyTrendDto(trendRes.value));
          setMonthlyTrendMeta({
            window: trendRes.value.window,
            excludedCount: trendRes.value.excludedCount,
            outOfWindowCount: trendRes.value.outOfWindowCount,
            currency: trendRes.value.currency,
          });
        } else if (!isAbortError(trendRes.reason)) {
          setMonthlyTrend([]);
          repErrors.push(formatApiErrorMessage(trendRes.reason));
        }

        if (exceptionsRes.status === 'fulfilled') {
          setReportExceptions(exceptionsRes.value.items);
          setReportExceptionsTotal(exceptionsRes.value.total);
        } else if (!isAbortError(exceptionsRes.reason)) {
          setReportExceptions([]);
          repErrors.push(formatApiErrorMessage(exceptionsRes.reason));
        }

        setWorkspaceError(
          primaryErrors.length > 0 ? primaryErrors.join(' ') : null
        );
        setReportsError(repErrors.length > 0 ? repErrors[0] : null);
      } finally {
        if (isLatestRequestSeq(workspaceSeqRef.current, reqSeq)) {
          setWorkspaceLoading(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    if (authStatus !== 'authenticated' || !activeWorkspaceId) {
      return;
    }
    void loadWorkspaceData(activeWorkspaceId);
    return () => {
      workspaceAbortRef.current?.abort();
    };
  }, [authStatus, activeWorkspaceId, loadWorkspaceData]);

  const loadSelectedInvoiceDetail = useCallback(
    async (workspaceId: string, invoiceId: string) => {
      detailAbortRef.current?.abort();
      if (!invoiceId) {
        setSelectedInvoiceDetail(null);
        setSelectedReviewHistory(null);
        setDetailError(null);
        setDetailLoading(false);
        return;
      }

      const controller = new AbortController();
      detailAbortRef.current = controller;
      const reqSeq = ++detailSeqRef.current;

      setDetailLoading(true);
      setDetailError(null);

      try {
        const [detailRes, historyRes] = await Promise.allSettled([
          apiClient.getInvoiceDetail(workspaceId, invoiceId, controller.signal),
          apiClient.getInvoiceReviewHistory(
            workspaceId,
            invoiceId,
            { order: 'desc', page: 1, pageSize: 50 },
            controller.signal
          ),
        ]);

        if (
          controller.signal.aborted ||
          !isLatestRequestSeq(detailSeqRef.current, reqSeq)
        ) {
          return;
        }

        if (detailRes.status === 'fulfilled') {
          setSelectedInvoiceDetail(mapInvoiceDetailDto(detailRes.value));
        } else if (!isAbortError(detailRes.reason)) {
          setSelectedInvoiceDetail(null);
          setDetailError(formatApiErrorMessage(detailRes.reason));
        }

        if (historyRes.status === 'fulfilled') {
          setSelectedReviewHistory(historyRes.value);
        } else if (!isAbortError(historyRes.reason)) {
          setSelectedReviewHistory(null);
        }
      } finally {
        if (isLatestRequestSeq(detailSeqRef.current, reqSeq)) {
          setDetailLoading(false);
        }
      }
    },
    []
  );

  useEffect(() => {
    if (
      authStatus !== 'authenticated' ||
      !activeWorkspaceId ||
      !selectedInvoiceId
    ) {
      if (!selectedInvoiceId) {
        setSelectedInvoiceDetail(null);
        setSelectedReviewHistory(null);
      }
      return;
    }
    void loadSelectedInvoiceDetail(activeWorkspaceId, selectedInvoiceId);
    return () => {
      detailAbortRef.current?.abort();
    };
  }, [
    authStatus,
    activeWorkspaceId,
    selectedInvoiceId,
    loadSelectedInvoiceDetail,
  ]);

  const activeWorkspace = useMemo(
    () =>
      workspaces.find((ws) => ws.workspaceId === activeWorkspaceId) ?? null,
    [workspaces, activeWorkspaceId]
  );

  const activeWorkspaceRole: WorkspaceRole | null =
    activeWorkspace?.role ?? null;

  const clearSessionExpiredMessage = useCallback(() => {
    setSessionExpiredMessage(null);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await apiClient.login(email, password);
      await hydrateSession();
    },
    [hydrateSession]
  );

  const register = useCallback(
    async (payload: RegisterApiPayload) => {
      await apiClient.register(payload);
      await hydrateSession();
    },
    [hydrateSession]
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.logout();
    } catch {
      // Clear local session view even if server cookie already expired
    } finally {
      clearSessionState(null);
    }
  }, [clearSessionState]);

  const performWorkspaceSwitch = useCallback(
    (nextWorkspaceId: string) => {
      if (nextWorkspaceId === activeWorkspaceId) return;
      resetWorkspaceData();
      writeStoredWorkspaceId(nextWorkspaceId);
      setActiveWorkspaceId(nextWorkspaceId);
    },
    [activeWorkspaceId, resetWorkspaceData]
  );

  const switchWorkspace = useCallback(
    (nextWorkspaceId: string) => {
      if (nextWorkspaceId === activeWorkspaceId) return;
      if (activeRoute === 'review' && hasUnsavedReviewChanges) {
        setPendingNavigation({ type: 'workspace', workspaceId: nextWorkspaceId });
        return;
      }
      performWorkspaceSwitch(nextWorkspaceId);
    },
    [
      activeRoute,
      activeWorkspaceId,
      hasUnsavedReviewChanges,
      performWorkspaceSwitch,
    ]
  );

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
    [
      activeRoute,
      hasUnsavedReviewChanges,
      performRouteNavigation,
      selectedInvoiceId,
    ]
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

    if (target.type === 'workspace') {
      performWorkspaceSwitch(target.workspaceId);
    } else if (target.type === 'invoice') {
      setSelectedInvoiceId(target.invoiceId);
      setActiveRoute('review');
    } else {
      performRouteNavigation(target.route, target.options);
    }
  }, [pendingNavigation, performRouteNavigation, performWorkspaceSwitch]);

  const clearSupplierFilter = useCallback(() => {
    setSupplierFilterId(null);
  }, []);

  const refreshWorkspace = useCallback(async () => {
    if (!activeWorkspaceId) return;
    await loadWorkspaceData(activeWorkspaceId);
  }, [activeWorkspaceId, loadWorkspaceData]);

  const refreshSelectedInvoiceDetail = useCallback(
    async (invoiceId?: string) => {
      if (!activeWorkspaceId) return;
      const targetId = invoiceId ?? selectedInvoiceId;
      if (!targetId) return;
      await loadSelectedInvoiceDetail(activeWorkspaceId, targetId);
    },
    [activeWorkspaceId, loadSelectedInvoiceDetail, selectedInvoiceId]
  );

  const loadTrendWindow = useCallback(
    async (window: '6m' | '12m' | 'all') => {
      if (!activeWorkspaceId) return;
      trendWindowRef.current = window;
      const res = await apiClient.getMonthlyTrend(activeWorkspaceId, {
        window,
      });
      setMonthlyTrend(mapMonthlyTrendDto(res));
      setMonthlyTrendMeta({
        window: res.window,
        excludedCount: res.excludedCount,
        outOfWindowCount: res.outOfWindowCount,
        currency: res.currency,
      });
    },
    [activeWorkspaceId]
  );

  const requireWorkspaceId = useCallback((): string => {
    if (!activeWorkspaceId) {
      throw new Error('No active workspace selected.');
    }
    return activeWorkspaceId;
  }, [activeWorkspaceId]);

  const uploadInvoiceFile = useCallback(
    async (params: {
      file: File;
      supplierName?: string;
      invoiceNumber?: string;
    }) => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const res = await apiClient.uploadDocument(wsId, {
          file: params.file,
          supplierName: params.supplierName,
          invoiceNumber: params.invoiceNumber,
          createDraftInvoice: true,
        });
        await loadWorkspaceData(wsId);
        if (res.invoiceId) {
          setSelectedInvoiceId(res.invoiceId);
          setActiveRoute('review');
        }
        return {
          documentId: res.document.id,
          invoiceId: res.invoiceId,
        };
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadWorkspaceData, requireWorkspaceId]
  );

  const createManualInvoice = useCallback(
    async (payload: InvoiceCreatePayload): Promise<Invoice> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const createdDto = await apiClient.createInvoice(wsId, payload);
        const mapped = mapInvoiceDetailDto(createdDto);
        setSelectedInvoiceDetail(mapped);
        setSelectedInvoiceId(mapped.id);
        await loadWorkspaceData(wsId);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadWorkspaceData, requireWorkspaceId]
  );

  const saveInvoiceChanges = useCallback(
    async (original: Invoice, draft: Invoice): Promise<Invoice> => {
      const wsId = requireWorkspaceId();
      const payload = buildInvoiceUpdatePayload(
        original,
        draft,
        activeWorkspaceRole
      );
      setMutationInFlight(true);
      try {
        const updatedDto = await apiClient.updateInvoice(
          wsId,
          original.id,
          payload
        );
        const mapped = mapInvoiceDetailDto(updatedDto);
        setSelectedInvoiceDetail(mapped);
        setHasUnsavedReviewChanges(false);
        await Promise.all([
          loadWorkspaceData(wsId),
          loadSelectedInvoiceDetail(wsId, original.id),
        ]);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [
      activeWorkspaceRole,
      loadSelectedInvoiceDetail,
      loadWorkspaceData,
      requireWorkspaceId,
    ]
  );

  const verifyInvoiceAction = useCallback(
    async (
      invoiceId: string,
      payload: VerifyInvoicePayload
    ): Promise<Invoice> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const updatedDto = await apiClient.verifyInvoice(
          wsId,
          invoiceId,
          payload
        );
        const mapped = mapInvoiceDetailDto(updatedDto);
        setSelectedInvoiceDetail(mapped);
        setHasUnsavedReviewChanges(false);
        await Promise.all([
          loadWorkspaceData(wsId),
          loadSelectedInvoiceDetail(wsId, invoiceId),
        ]);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadSelectedInvoiceDetail, loadWorkspaceData, requireWorkspaceId]
  );

  const flagInvoiceAction = useCallback(
    async (
      invoiceId: string,
      payload: FlagInvoicePayload
    ): Promise<Invoice> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const updatedDto = await apiClient.flagInvoice(wsId, invoiceId, payload);
        const mapped = mapInvoiceDetailDto(updatedDto);
        setSelectedInvoiceDetail(mapped);
        setHasUnsavedReviewChanges(false);
        await Promise.all([
          loadWorkspaceData(wsId),
          loadSelectedInvoiceDetail(wsId, invoiceId),
        ]);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadSelectedInvoiceDetail, loadWorkspaceData, requireWorkspaceId]
  );

  const resolveFlagAction = useCallback(
    async (flagId: string, payload: ResolveFlagPayload): Promise<void> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const res = await apiClient.resolveReviewFlag(wsId, flagId, payload);
        await Promise.all([
          loadWorkspaceData(wsId),
          loadSelectedInvoiceDetail(wsId, res.invoiceId),
        ]);
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadSelectedInvoiceDetail, loadWorkspaceData, requireWorkspaceId]
  );

  const reopenInvoiceAction = useCallback(
    async (invoiceId: string, reason: string): Promise<Invoice> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const updatedDto = await apiClient.reopenInvoice(
          wsId,
          invoiceId,
          reason
        );
        const mapped = mapInvoiceDetailDto(updatedDto);
        setSelectedInvoiceDetail(mapped);
        await Promise.all([
          loadWorkspaceData(wsId),
          loadSelectedInvoiceDetail(wsId, invoiceId),
        ]);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadSelectedInvoiceDetail, loadWorkspaceData, requireWorkspaceId]
  );

  const deleteInvoiceAction = useCallback(
    async (invoiceId: string, deletionReason?: string): Promise<void> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        await apiClient.deleteInvoice(wsId, invoiceId, deletionReason);
        if (selectedInvoiceId === invoiceId) {
          setSelectedInvoiceId('');
          setSelectedInvoiceDetail(null);
          setSelectedReviewHistory(null);
          setHasUnsavedReviewChanges(false);
        }
        await loadWorkspaceData(wsId);
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadWorkspaceData, requireWorkspaceId, selectedInvoiceId]
  );

  const createSupplierAction = useCallback(
    async (payload: SupplierCreatePayload): Promise<SupplierSummary> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const created = await apiClient.createSupplier(wsId, payload);
        await loadWorkspaceData(wsId);
        return mapSupplierSummaryDto(created);
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadWorkspaceData, requireWorkspaceId]
  );

  const updateSupplierAction = useCallback(
    async (
      supplierId: string,
      payload: SupplierUpdatePayload
    ): Promise<SupplierSummary> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const updated = await apiClient.updateSupplier(
          wsId,
          supplierId,
          payload
        );
        await loadWorkspaceData(wsId);
        return mapSupplierSummaryDto(updated);
      } finally {
        setMutationInFlight(false);
      }
    },
    [loadWorkspaceData, requireWorkspaceId]
  );

  const updateSettingsAction = useCallback(
    async (
      payload: WorkspaceSettingsUpdatePayload
    ): Promise<WorkspaceSettings> => {
      const wsId = requireWorkspaceId();
      setMutationInFlight(true);
      try {
        const updatedDto = await apiClient.updateWorkspaceSettings(
          wsId,
          payload
        );
        const mapped = mapWorkspaceSettingsDto(
          updatedDto,
          activeWorkspace
            ? {
                id: activeWorkspace.workspaceId,
                organizationId: activeWorkspace.organizationId,
                name: activeWorkspace.name,
                workspaceCode: activeWorkspace.workspaceCode,
                isActive: true,
                currentUserRole: activeWorkspace.role,
                createdAt: '',
              }
            : null,
          organizationsRef.current
        );
        setSettings(mapped);
        return mapped;
      } finally {
        setMutationInFlight(false);
      }
    },
    [activeWorkspace, requireWorkspaceId]
  );

  const exportCsvReport = useCallback(
    async (params?: {
      status?: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
      dateFrom?: string;
      dateTo?: string;
      currency?: string;
    }): Promise<string> => {
      const wsId = requireWorkspaceId();
      const { filename, blob } = await apiClient.downloadReportCsv(wsId, params);

      if (typeof document !== 'undefined' && typeof URL !== 'undefined') {
        const url = URL.createObjectURL(blob);
        try {
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.download = filename;
          document.body.appendChild(anchor);
          anchor.click();
          document.body.removeChild(anchor);
        } finally {
          URL.revokeObjectURL(url);
        }
      }

      void loadWorkspaceData(wsId);
      return filename;
    },
    [loadWorkspaceData, requireWorkspaceId]
  );

  const updateLocalUiPrefs = useCallback((prefs: LocalUiPreferences) => {
    setLocalUiPrefs(prefs);
    saveLocalUiPrefs(prefs);
  }, []);

  const activities = useMemo<ActivityEvent[]>(
    () => auditEvents.map(mapAuditEventToActivity),
    [auditEvents]
  );

  const derivedNotifications = useMemo<NotificationItem[]>(() => {
    const items: NotificationItem[] = [];
    for (const inv of invoices) {
      if (inv.status === 'Flagged') {
        const id = `flagged:${inv.id}:${inv.updatedAt ?? inv.status}`;
        items.push({
          id,
          title: `Flagged invoice: ${inv.invoiceNumber}`,
          detail: `${inv.supplierName} requires secondary human review.`,
          timeLabel: inv.uploadDate,
          read: readNotificationIds.has(id),
          targetRoute: 'review',
          targetInvoiceId: inv.id,
          category: 'flagged',
        });
      }
      if (inv.duplicateWarning) {
        const id = `dup:${inv.id}:${inv.updatedAt ?? inv.invoiceNumber}`;
        items.push({
          id,
          title: `Duplicate warning: ${inv.invoiceNumber}`,
          detail: inv.duplicateWarning,
          timeLabel: inv.uploadDate,
          read: readNotificationIds.has(id),
          targetRoute: 'review',
          targetInvoiceId: inv.id,
          category: 'duplicate',
        });
      }
    }
    return filterNotificationsBySettings(items, settings).slice(0, 12);
  }, [invoices, readNotificationIds, settings]);

  const markNotificationRead = useCallback((id: string) => {
    setReadNotificationIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  const markAllNotificationsRead = useCallback(() => {
    setReadNotificationIds((prev) => {
      const next = new Set(prev);
      for (const item of derivedNotifications) {
        next.add(item.id);
      }
      return next;
    });
  }, [derivedNotifications]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      authStatus,
      currentUser,
      organizations,
      workspaces,
      activeWorkspaceId,
      activeWorkspace,
      activeWorkspaceRole,
      sessionExpiredMessage,
      clearSessionExpiredMessage,
      login,
      register,
      logout,
      switchWorkspace,
      activeRoute,
      navigate,
      invoices,
      invoicesTotal,
      suppliers,
      activities,
      auditEvents,
      auditEventsTotal,
      reportSummary,
      monthlyTrend,
      monthlyTrendMeta,
      reportExceptions,
      reportExceptionsTotal,
      notifications: derivedNotifications,
      settings,
      localUiPrefs,
      updateLocalUiPrefs,
      workspaceLoading,
      workspaceError,
      reportsError,
      mutationInFlight,
      selectedInvoiceId,
      selectedInvoiceDetail,
      selectedReviewHistory,
      detailLoading,
      detailError,
      selectInvoiceForReview,
      refreshSelectedInvoiceDetail,
      hasUnsavedReviewChanges,
      setHasUnsavedReviewChanges,
      pendingNavigation,
      cancelPendingNavigation,
      commitPendingNavigation,
      supplierFilterId,
      clearSupplierFilter,
      refreshWorkspace,
      loadTrendWindow,
      uploadInvoiceFile,
      createManualInvoice,
      saveInvoiceChanges,
      verifyInvoiceAction,
      flagInvoiceAction,
      resolveFlagAction,
      reopenInvoiceAction,
      deleteInvoiceAction,
      createSupplierAction,
      updateSupplierAction,
      updateSettingsAction,
      exportCsvReport,
      markNotificationRead,
      markAllNotificationsRead,
    }),
    [
      authStatus,
      currentUser,
      organizations,
      workspaces,
      activeWorkspaceId,
      activeWorkspace,
      activeWorkspaceRole,
      sessionExpiredMessage,
      clearSessionExpiredMessage,
      login,
      register,
      logout,
      switchWorkspace,
      activeRoute,
      navigate,
      invoices,
      invoicesTotal,
      suppliers,
      activities,
      auditEvents,
      auditEventsTotal,
      reportSummary,
      monthlyTrend,
      monthlyTrendMeta,
      reportExceptions,
      reportExceptionsTotal,
      derivedNotifications,
      settings,
      localUiPrefs,
      updateLocalUiPrefs,
      workspaceLoading,
      workspaceError,
      reportsError,
      mutationInFlight,
      selectedInvoiceId,
      selectedInvoiceDetail,
      selectedReviewHistory,
      detailLoading,
      detailError,
      selectInvoiceForReview,
      refreshSelectedInvoiceDetail,
      hasUnsavedReviewChanges,
      pendingNavigation,
      cancelPendingNavigation,
      commitPendingNavigation,
      supplierFilterId,
      clearSupplierFilter,
      refreshWorkspace,
      loadTrendWindow,
      uploadInvoiceFile,
      createManualInvoice,
      saveInvoiceChanges,
      verifyInvoiceAction,
      flagInvoiceAction,
      resolveFlagAction,
      reopenInvoiceAction,
      deleteInvoiceAction,
      createSupplierAction,
      updateSupplierAction,
      updateSettingsAction,
      exportCsvReport,
      markNotificationRead,
      markAllNotificationsRead,
    ]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return ctx;
}
