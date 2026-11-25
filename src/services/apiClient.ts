import {
  DEMO_MODE_DISABLED_ACTION_MESSAGE,
  isDemoModeEnabled,
} from '../config/demoMode';
import type {
  ApiAuditEvent,
  ApiDuplicateMatch,
  ApiReconciliationStatus,
  ApiReportExceptionItem,
  ApiReportSummary,
  ApiReviewFlag,
  ApiReviewHistory,
  AuthenticatedUser,
  DocumentScanStatus,
  FlagCategory,
  OrgRole,
  OrganizationSummary,
  WorkspaceMembershipSummary,
  WorkspaceRole,
} from '../types/domain';

export const CSRF_COOKIE_NAME = 'norus_csrf_token';
export const CSRF_HEADER_NAME = 'X-CSRF-Token';

export interface BackendErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> | null;
    requestId?: string | null;
  };
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;
  readonly requestId: string | null;

  constructor(params: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
    requestId?: string | null;
  }) {
    super(params.message);
    this.name = 'ApiClientError';
    this.status = params.status;
    this.code = params.code;
    this.details = params.details ?? null;
    this.requestId = params.requestId ?? null;
  }
}

export interface RegisterApiPayload {
  email: string;
  password: string;
  fullName: string;
  organizationName?: string;
  firmType?: string;
}

export interface LoginResponseDto {
  user: AuthenticatedUser;
  workspaces: WorkspaceMembershipSummary[];
  sessionExpiresAt: string;
}

export interface RegisterResponseDto {
  user: AuthenticatedUser;
  organization: OrganizationSummary | null;
  workspace: WorkspaceMembershipSummary | null;
  sessionExpiresAt: string;
}

export interface MeResponseDto {
  user: AuthenticatedUser;
  organizations: OrganizationSummary[];
  workspaces: WorkspaceMembershipSummary[];
}

export interface WorkspaceDetailDto {
  id: string;
  organizationId: string;
  name: string;
  workspaceCode: string;
  isActive: boolean;
  currentUserRole: WorkspaceRole;
  createdAt: string;
}

export interface WorkspaceSettingsDto {
  workspaceId: string;
  legalEntityName: string;
  companyGstin: string | null;
  companyPan: string | null;
  registeredAddress: string;
  requireHumanReview: true;
  enableDuplicateWarnings: boolean;
  autoFlagTaxMismatch: boolean;
  roundingTolerance: string;
  defaultCurrency: string;
  financialYear: string;
  dateFormat: string;
  taxRegime: string;
  notifyFlaggedInvoices: boolean;
  notifyDailyDigest: boolean;
  notifyDuplicateAlerts: boolean;
  updatedAt: string;
}

export interface WorkspaceSettingsUpdatePayload {
  legalEntityName?: string;
  companyGstin?: string | null;
  companyPan?: string | null;
  registeredAddress?: string;
  enableDuplicateWarnings?: boolean;
  autoFlagTaxMismatch?: boolean;
  roundingTolerance?: string;
  defaultCurrency?: string;
  financialYear?: string;
  dateFormat?: string;
  taxRegime?: string;
  notifyFlaggedInvoices?: boolean;
  notifyDailyDigest?: boolean;
  notifyDuplicateAlerts?: boolean;
}

export interface SupplierSummaryDto {
  id: string;
  workspaceId: string;
  name: string;
  normalizedName: string;
  gstin: string | null;
  pan: string | null;
  stateCode: string | null;
  stateName: string | null;
  category: string;
  email: string | null;
  status: 'VERIFIED' | 'NEEDS_VERIFICATION' | 'FLAGGED';
  createdAt: string;
  updatedAt: string;
  totalInvoices: number;
  totalValue: string;
  lastInvoiceDate: string | null;
}

export interface SupplierListResponseDto {
  items: SupplierSummaryDto[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SupplierCreatePayload {
  name: string;
  gstin?: string | null;
  pan?: string | null;
  stateCode?: string | null;
  stateName?: string | null;
  category?: string;
  email?: string | null;
  status?: 'VERIFIED' | 'NEEDS_VERIFICATION' | 'FLAGGED';
}

export interface SupplierUpdatePayload extends Partial<SupplierCreatePayload> {}

export interface DocumentDto {
  id: string;
  workspaceId: string;
  uploadedByUserId: string | null;
  originalFilename: string;
  mimeType: string;
  byteSize: number;
  sha256Checksum: string;
  pageCount: number;
  scanStatus: DocumentScanStatus;
  createdAt: string;
}

export interface DocumentUploadResponseDto {
  document: DocumentDto;
  invoiceId: string | null;
}

export interface InvoiceLineItemDto {
  id: string;
  sortOrder: number;
  description: string;
  hsnSac: string | null;
  quantity: string;
  unitPrice: string;
  taxRatePercent: string;
  taxableValue: string;
}

export interface InvoiceFieldVerificationDto {
  id: string;
  fieldKey: string;
  status: 'VERIFIED' | 'NEEDS_REVIEW' | 'FLAGGED';
  evidenceNote: string;
  sourcePage: number | null;
  boundingBox: Record<string, unknown> | null;
  confidenceScore: string | null;
  verifiedByUserId: string | null;
  updatedAt: string;
}

export interface InvoiceSummaryDto {
  id: string;
  workspaceId: string;
  supplierId: string | null;
  documentId: string | null;
  supplierName: string;
  supplierGstin: string | null;
  buyerName: string | null;
  buyerGstin: string | null;
  placeOfSupplyCode: string | null;
  placeOfSupplyName: string | null;
  invoiceNumber: string;
  normalizedInvoiceNumber: string;
  invoiceDate: string | null;
  dueDate: string | null;
  uploadDate: string;
  financialYear: string | null;
  currency: string;
  isReverseCharge: boolean;
  taxType: 'INTRA_STATE' | 'INTER_STATE' | 'MIXED' | 'NONE';
  taxableAmount: string;
  discountAmount: string;
  discountMode: 'BEFORE_TAX' | 'AFTER_TAX';
  cgstAmount: string;
  sgstAmount: string;
  igstAmount: string;
  cessAmount: string;
  taxAmount: string;
  freightAmount: string;
  otherChargesAmount: string;
  roundOffAmount: string;
  totalAmount: string;
  computedExpectedTotal: string;
  varianceAmount: string;
  reconciliationStatus: ApiReconciliationStatus;
  lineItemsTaxableSum: string | null;
  lineItemVarianceAmount: string | null;
  lineItemReconciliationStatus: 'NO_LINE_ITEMS' | 'MATCHED' | 'VARIANCE_WARNING';
  lineItemWarning: string | null;
  status: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
  duplicateWarning: string | null;
  reviewerNote: string;
  sourceType: 'MANUAL' | 'DOCUMENT_UPLOAD' | 'IMPORT';
  verifiedByUserId: string | null;
  verifiedAt: string | null;
  lineItemCount: number;
  openFlagCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface InvoiceDetailDto extends InvoiceSummaryDto {
  document: {
    id: string;
    originalFilename: string;
    mimeType: string;
    byteSize: number;
    pageCount: number;
    scanStatus: DocumentScanStatus;
    createdAt: string;
  } | null;
  lineItems: InvoiceLineItemDto[];
  fieldVerifications: InvoiceFieldVerificationDto[];
  reviewFlags: ApiReviewFlag[];
  reconciliation: {
    roundingTolerance: string;
    computedExpectedTotal: string;
    declaredTotal: string;
    varianceAmount: string;
    reconciliationStatus: ApiReconciliationStatus;
    lineItemsTaxableSum: string | null;
    lineItemVarianceAmount: string | null;
    lineItemReconciliationStatus: 'NO_LINE_ITEMS' | 'MATCHED' | 'VARIANCE_WARNING';
    lineItemWarning: string | null;
    discrepancies: Array<{
      code: string;
      severity: 'info' | 'warning' | 'error' | 'INFO' | 'WARNING';
      message: string;
      details: Record<string, unknown>;
    }>;
  };
  duplicateMatches: ApiDuplicateMatch[];
}

export interface InvoiceListResponseDto {
  items: InvoiceSummaryDto[];
  total: number;
  page: number;
  pageSize: number;
}

export interface InvoiceUpdatePayload {
  supplierName?: string;
  supplierGstin?: string | null;
  invoiceNumber?: string;
  invoiceDate?: string | null;
  taxableAmount?: string;
  cgstAmount?: string;
  sgstAmount?: string;
  igstAmount?: string;
  totalAmount?: string;
  reviewerNote?: string;
  fieldVerifications?: Array<{
    fieldKey: string;
    status: 'VERIFIED' | 'NEEDS_REVIEW' | 'FLAGGED';
    evidenceNote?: string;
  }>;
}

export interface InvoiceCreatePayload {
  supplierId?: string | null;
  supplierName?: string;
  supplierGstin?: string | null;
  invoiceNumber: string;
  invoiceDate?: string | null;
  taxableAmount?: string;
  cgstAmount?: string;
  sgstAmount?: string;
  igstAmount?: string;
  totalAmount?: string;
  reviewerNote?: string;
}

export interface VerifyInvoicePayload {
  confirmVarianceAcknowledgment?: boolean;
  confirmationNote?: string;
  resolveOpenFlags?: boolean;
  flagResolutionNote?: string;
  fieldVerifications?: Array<{
    fieldKey: string;
    status: 'VERIFIED';
    evidenceNote?: string;
  }>;
}

export interface FlagInvoicePayload {
  flagCategory: FlagCategory;
  reasonText: string;
  fieldKey?: string;
}

export interface ResolveFlagPayload {
  resolutionStatus: 'RESOLVED' | 'DISMISSED';
  resolutionNote: string;
  reopenToPending?: boolean;
}

export interface ResolveFlagResponseDto {
  flag: ApiReviewFlag;
  invoiceId: string;
  invoiceStatus: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
  openFlagCount: number;
}

export interface MonthlyTrendResponseDto {
  workspaceId: string;
  window: '6m' | '12m' | 'all';
  currency: string;
  buckets: Array<{
    monthKey: string;
    label: string;
    totalCount: number;
    verifiedCount: number;
    pendingCount: number;
    flaggedCount: number;
    totalValue: string;
    totalTaxableValue: string;
    totalGst: string;
  }>;
  excludedCount: number;
  outOfWindowCount: number;
}

export interface ReportExceptionsResponseDto {
  items: ApiReportExceptionItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface AuditEventListResponseDto {
  items: ApiAuditEvent[];
  total: number;
  page: number;
  pageSize: number;
}

const MUTATING_METHODS = new Set(['POST', 'PATCH', 'PUT', 'DELETE']);
const CSRF_EXEMPT_PATHS = new Set(['/auth/login', '/auth/register']);

export function resolveApiBaseUrl(configuredBaseUrl?: string): string {
  const envUrl =
    configuredBaseUrl ??
    ((import.meta as unknown as { env?: Record<string, string | undefined> }).env
      ?.VITE_API_BASE_URL ??
      '');
  const trimmed = envUrl.trim().replace(/\/+$/, '');
  if (!trimmed) return '/api/v1';
  if (trimmed.endsWith('/api/v1')) return trimmed;
  return `${trimmed}/api/v1`;
}

export function extractCookieValue(
  cookieHeader: string | undefined | null,
  name: string
): string | null {
  if (!cookieHeader) return null;
  const pairs = cookieHeader.split(';');
  for (const rawPair of pairs) {
    const eqIndex = rawPair.indexOf('=');
    if (eqIndex <= 0) continue;
    const key = rawPair.slice(0, eqIndex).trim();
    if (key === name) {
      const value = rawPair.slice(eqIndex + 1).trim();
      try {
        return decodeURIComponent(value);
      } catch {
        return value;
      }
    }
  }
  return null;
}

export function getBrowserCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  return extractCookieValue(document.cookie, CSRF_COOKIE_NAME);
}

export function buildApiUrl(
  baseUrl: string,
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>
): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const fullPath = `${baseUrl.replace(/\/+$/, '')}${normalizedPath}`;
  if (!query) return fullPath;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${fullPath}?${qs}` : fullPath;
}

export async function parseApiErrorResponse(
  response: Response
): Promise<ApiClientError> {
  const status = response.status;
  let code = `HTTP_${status}`;
  let message = response.statusText || `Request failed with status ${status}`;
  let details: Record<string, unknown> | null = null;
  let requestId: string | null = null;

  try {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const body = (await response.json()) as BackendErrorEnvelope;
      if (body?.error) {
        if (body.error.code) code = body.error.code;
        if (body.error.message) message = body.error.message;
        details = body.error.details ?? null;
        requestId = body.error.requestId ?? null;
      }
    }
  } catch {
    // Keep fallback status/message when body is unreadable
  }

  return new ApiClientError({ status, code, message, details, requestId });
}

export function extractFilenameFromContentDisposition(
  headerValue: string | null,
  fallback: string
): string {
  if (!headerValue) return fallback;
  const match = /filename="?([^";\n]+)"?/i.exec(headerValue);
  return match?.[1]?.trim() || fallback;
}

export function formatApiErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.code === 'DEMO_MODE_API_BLOCKED') {
      return DEMO_MODE_DISABLED_ACTION_MESSAGE;
    }
    if (err.code === 'NETWORK_ERROR') {
      return 'Unable to reach the NORUS BILLWISE API server. Verify the backend is running.';
    }
    if (err.code === 'VARIANCE_ACKNOWLEDGMENT_REQUIRED') {
      return err.message;
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return 'An unexpected error occurred.';
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly demoModeChecker: () => boolean;
  private refreshPromise: Promise<boolean> | null = null;
  private unauthorizedHandler: (() => void) | null = null;

  constructor(options?: {
    baseUrl?: string;
    fetchImpl?: typeof fetch;
    demoModeChecker?: () => boolean;
  }) {
    this.baseUrl = resolveApiBaseUrl(options?.baseUrl);
    this.fetchImpl = options?.fetchImpl ?? ((input, init) => fetch(input, init));
    this.demoModeChecker = options?.demoModeChecker ?? isDemoModeEnabled;
  }

  setUnauthorizedHandler(handler: (() => void) | null): void {
    this.unauthorizedHandler = handler;
  }

  getDocumentContentUrl(
    workspaceId: string,
    documentId: string,
    download = false
  ): string {
    return buildApiUrl(
      this.baseUrl,
      `/workspaces/${workspaceId}/documents/${documentId}/content`,
      download ? { download: true } : undefined
    );
  }

  private async tryRefreshSession(): Promise<boolean> {
    if (this.demoModeChecker()) {
      return false;
    }
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      try {
        const headers = new Headers();
        const csrf = getBrowserCsrfToken();
        if (csrf) {
          headers.set(CSRF_HEADER_NAME, csrf);
        }
        const res = await this.fetchImpl(
          buildApiUrl(this.baseUrl, '/auth/refresh'),
          {
            method: 'POST',
            credentials: 'include',
            headers,
          }
        );
        return res.ok;
      } catch {
        return false;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async requestRaw(
    path: string,
    options: {
      method?: string;
      query?: Record<string, string | number | boolean | undefined | null>;
      body?: unknown;
      signal?: AbortSignal;
      skipAuthRefresh?: boolean;
    } = {},
    allowRefreshRetry = true
  ): Promise<Response> {
    if (this.demoModeChecker()) {
      throw new ApiClientError({
        status: 0,
        code: 'DEMO_MODE_API_BLOCKED',
        message: DEMO_MODE_DISABLED_ACTION_MESSAGE,
      });
    }

    const method = (options.method ?? 'GET').toUpperCase();
    const url = buildApiUrl(this.baseUrl, path, options.query);
    const headers = new Headers();

    let requestBody: BodyInit | undefined;
    if (options.body instanceof FormData) {
      requestBody = options.body;
    } else if (options.body !== undefined) {
      headers.set('Content-Type', 'application/json');
      requestBody = JSON.stringify(options.body);
    }

    if (MUTATING_METHODS.has(method) && !CSRF_EXEMPT_PATHS.has(path)) {
      const csrf = getBrowserCsrfToken();
      if (csrf) {
        headers.set(CSRF_HEADER_NAME, csrf);
      }
    }

    let response: Response;
    try {
      response = await this.fetchImpl(url, {
        method,
        headers,
        body: requestBody,
        credentials: 'include',
        signal: options.signal,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw err;
      }
      throw new ApiClientError({
        status: 0,
        code: 'NETWORK_ERROR',
        message: 'Network connection error while contacting backend API.',
      });
    }

    const canAttemptRefresh =
      allowRefreshRetry &&
      !options.skipAuthRefresh &&
      response.status === 401 &&
      !path.startsWith('/auth/login') &&
      !path.startsWith('/auth/register') &&
      !path.startsWith('/auth/refresh') &&
      !path.startsWith('/auth/logout');

    if (canAttemptRefresh) {
      const refreshed = await this.tryRefreshSession();
      if (refreshed) {
        return this.requestRaw(path, options, false);
      }
    }

    if (!response.ok) {
      if (response.status === 401 && !options.skipAuthRefresh) {
        this.unauthorizedHandler?.();
      }
      throw await parseApiErrorResponse(response);
    }

    return response;
  }

  async requestJson<T>(
    path: string,
    options: {
      method?: string;
      query?: Record<string, string | number | boolean | undefined | null>;
      body?: unknown;
      signal?: AbortSignal;
      skipAuthRefresh?: boolean;
    } = {}
  ): Promise<T> {
    const res = await this.requestRaw(path, options);
    if (res.status === 204) {
      return undefined as T;
    }
    return (await res.json()) as T;
  }

  // --- Authentication ---
  login(email: string, password: string): Promise<LoginResponseDto> {
    return this.requestJson<LoginResponseDto>('/auth/login', {
      method: 'POST',
      body: { email, password },
      skipAuthRefresh: true,
    });
  }

  register(payload: RegisterApiPayload): Promise<RegisterResponseDto> {
    return this.requestJson<RegisterResponseDto>('/auth/register', {
      method: 'POST',
      body: payload,
      skipAuthRefresh: true,
    });
  }

  logout(): Promise<void> {
    return this.requestJson<void>('/auth/logout', {
      method: 'POST',
      skipAuthRefresh: true,
    });
  }

  getMe(signal?: AbortSignal): Promise<MeResponseDto> {
    return this.requestJson<MeResponseDto>('/auth/me', { signal });
  }

  // --- Workspaces & Settings ---
  getWorkspaceDetail(
    workspaceId: string,
    signal?: AbortSignal
  ): Promise<WorkspaceDetailDto> {
    return this.requestJson<WorkspaceDetailDto>(`/workspaces/${workspaceId}`, {
      signal,
    });
  }

  getWorkspaceSettings(
    workspaceId: string,
    signal?: AbortSignal
  ): Promise<WorkspaceSettingsDto> {
    return this.requestJson<WorkspaceSettingsDto>(
      `/workspaces/${workspaceId}/settings`,
      { signal }
    );
  }

  updateWorkspaceSettings(
    workspaceId: string,
    payload: WorkspaceSettingsUpdatePayload
  ): Promise<WorkspaceSettingsDto> {
    return this.requestJson<WorkspaceSettingsDto>(
      `/workspaces/${workspaceId}/settings`,
      {
        method: 'PATCH',
        body: payload,
      }
    );
  }

  // --- Suppliers ---
  listSuppliers(
    workspaceId: string,
    params?: {
      search?: string;
      status?: 'VERIFIED' | 'NEEDS_VERIFICATION' | 'FLAGGED';
      page?: number;
      pageSize?: number;
    },
    signal?: AbortSignal
  ): Promise<SupplierListResponseDto> {
    return this.requestJson<SupplierListResponseDto>(
      `/workspaces/${workspaceId}/suppliers`,
      { query: params, signal }
    );
  }

  createSupplier(
    workspaceId: string,
    payload: SupplierCreatePayload
  ): Promise<SupplierSummaryDto> {
    return this.requestJson<SupplierSummaryDto>(
      `/workspaces/${workspaceId}/suppliers`,
      { method: 'POST', body: payload }
    );
  }

  updateSupplier(
    workspaceId: string,
    supplierId: string,
    payload: SupplierUpdatePayload
  ): Promise<SupplierSummaryDto> {
    return this.requestJson<SupplierSummaryDto>(
      `/workspaces/${workspaceId}/suppliers/${supplierId}`,
      { method: 'PATCH', body: payload }
    );
  }

  // --- Documents ---
  uploadDocument(
    workspaceId: string,
    params: {
      file: File;
      supplierName?: string;
      invoiceNumber?: string;
      createDraftInvoice?: boolean;
    }
  ): Promise<DocumentUploadResponseDto> {
    const formData = new FormData();
    formData.append('file', params.file);
    if (params.supplierName?.trim()) {
      formData.append('supplierName', params.supplierName.trim());
    }
    if (params.invoiceNumber?.trim()) {
      formData.append('invoiceNumber', params.invoiceNumber.trim());
    }
    formData.append(
      'createDraftInvoice',
      String(params.createDraftInvoice ?? true)
    );
    return this.requestJson<DocumentUploadResponseDto>(
      `/workspaces/${workspaceId}/documents`,
      {
        method: 'POST',
        body: formData,
      }
    );
  }

  // --- Invoices ---
  listInvoices(
    workspaceId: string,
    params?: {
      search?: string;
      status?: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
      taxType?: 'INTRA_STATE' | 'INTER_STATE';
      supplierId?: string;
      sortBy?: string;
      sortDir?: 'asc' | 'desc';
      page?: number;
      pageSize?: number;
    },
    signal?: AbortSignal
  ): Promise<InvoiceListResponseDto> {
    return this.requestJson<InvoiceListResponseDto>(
      `/workspaces/${workspaceId}/invoices`,
      { query: params, signal }
    );
  }

  getInvoiceDetail(
    workspaceId: string,
    invoiceId: string,
    signal?: AbortSignal
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}`,
      { signal }
    );
  }

  createInvoice(
    workspaceId: string,
    payload: InvoiceCreatePayload
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices`,
      {
        method: 'POST',
        body: payload,
      }
    );
  }

  updateInvoice(
    workspaceId: string,
    invoiceId: string,
    payload: InvoiceUpdatePayload
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}`,
      {
        method: 'PATCH',
        body: payload,
      }
    );
  }

  deleteInvoice(
    workspaceId: string,
    invoiceId: string,
    deletionReason?: string
  ): Promise<void> {
    return this.requestJson<void>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}`,
      {
        method: 'DELETE',
        body: deletionReason ? { deletionReason } : undefined,
      }
    );
  }

  // --- Human Review ---
  verifyInvoice(
    workspaceId: string,
    invoiceId: string,
    payload: VerifyInvoicePayload
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}/verify`,
      {
        method: 'POST',
        body: payload,
      }
    );
  }

  flagInvoice(
    workspaceId: string,
    invoiceId: string,
    payload: FlagInvoicePayload
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}/flag`,
      {
        method: 'POST',
        body: payload,
      }
    );
  }

  resolveReviewFlag(
    workspaceId: string,
    flagId: string,
    payload: ResolveFlagPayload
  ): Promise<ResolveFlagResponseDto> {
    return this.requestJson<ResolveFlagResponseDto>(
      `/workspaces/${workspaceId}/flags/${flagId}/resolve`,
      {
        method: 'POST',
        body: payload,
      }
    );
  }

  reopenInvoice(
    workspaceId: string,
    invoiceId: string,
    reason: string
  ): Promise<InvoiceDetailDto> {
    return this.requestJson<InvoiceDetailDto>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}/reopen`,
      {
        method: 'POST',
        body: { reason },
      }
    );
  }

  getInvoiceReviewHistory(
    workspaceId: string,
    invoiceId: string,
    params?: { order?: 'asc' | 'desc'; page?: number; pageSize?: number },
    signal?: AbortSignal
  ): Promise<ApiReviewHistory> {
    return this.requestJson<ApiReviewHistory>(
      `/workspaces/${workspaceId}/invoices/${invoiceId}/review-history`,
      { query: params, signal }
    );
  }

  // --- Reports & Audit ---
  getReportSummary(
    workspaceId: string,
    params?: { dateFrom?: string; dateTo?: string; currency?: string },
    signal?: AbortSignal
  ): Promise<ApiReportSummary> {
    return this.requestJson<ApiReportSummary>(
      `/workspaces/${workspaceId}/reports/summary`,
      { query: params, signal }
    );
  }

  getMonthlyTrend(
    workspaceId: string,
    params?: { window?: '6m' | '12m' | 'all'; currency?: string },
    signal?: AbortSignal
  ): Promise<MonthlyTrendResponseDto> {
    return this.requestJson<MonthlyTrendResponseDto>(
      `/workspaces/${workspaceId}/reports/monthly-trend`,
      { query: params, signal }
    );
  }

  listReportExceptions(
    workspaceId: string,
    params?: {
      search?: string;
      status?: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
      flagCategory?: FlagCategory;
      dateFrom?: string;
      dateTo?: string;
      page?: number;
      pageSize?: number;
    },
    signal?: AbortSignal
  ): Promise<ReportExceptionsResponseDto> {
    return this.requestJson<ReportExceptionsResponseDto>(
      `/workspaces/${workspaceId}/reports/exceptions`,
      { query: params, signal }
    );
  }

  async downloadReportCsv(
    workspaceId: string,
    params?: {
      status?: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
      dateFrom?: string;
      dateTo?: string;
      currency?: string;
    }
  ): Promise<{ filename: string; blob: Blob }> {
    const res = await this.requestRaw(
      `/workspaces/${workspaceId}/reports/export.csv`,
      { query: params }
    );
    const fallback = `norus-billwise-report-${new Date().toISOString().slice(0, 10)}.csv`;
    const filename = extractFilenameFromContentDisposition(
      res.headers.get('content-disposition'),
      fallback
    );
    const blob = await res.blob();
    return { filename, blob };
  }

  listAuditEvents(
    workspaceId: string,
    params?: {
      entityType?: string;
      entityId?: string;
      eventType?: string;
      actorUserId?: string;
      dateFrom?: string;
      dateTo?: string;
      page?: number;
      pageSize?: number;
    },
    signal?: AbortSignal
  ): Promise<AuditEventListResponseDto> {
    return this.requestJson<AuditEventListResponseDto>(
      `/workspaces/${workspaceId}/audit-events`,
      { query: params, signal }
    );
  }
}

export const apiClient = new ApiClient();
export type { OrgRole };
