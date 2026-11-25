export type AppRoute =
  | 'dashboard'
  | 'invoices'
  | 'review'
  | 'suppliers'
  | 'reports'
  | 'settings';

export type InvoiceStatus = 'Pending Review' | 'Verified' | 'Flagged';

export type FieldVerificationStatus = 'Verified' | 'Needs Review' | 'Flagged';

export type SupplierStatus = 'Verified' | 'Needs Verification' | 'Flagged';

export type InvoiceFieldKey =
  | 'supplierName'
  | 'supplierGstin'
  | 'invoiceNumber'
  | 'invoiceDate'
  | 'taxableAmount'
  | 'cgst'
  | 'sgst'
  | 'igst'
  | 'totalAmount';

export interface InvoiceLineItem {
  id: string;
  description: string;
  hsnSac: string;
  quantity: number;
  unitPrice: number;
  taxRatePercent: number;
  taxableValue: number;
}

export interface InvoiceFieldMeta {
  status: FieldVerificationStatus;
  evidenceNote: string;
}

export type WorkspaceRole =
  | 'WORKSPACE_ADMIN'
  | 'REVIEWER'
  | 'UPLOADER'
  | 'VIEWER';

export type OrgRole = 'ORG_OWNER' | 'ORG_ADMIN' | 'ORG_MEMBER';

export type DocumentScanStatus =
  | 'PENDING'
  | 'CLEAN'
  | 'INFECTED'
  | 'FAILED'
  | 'SKIPPED_DEV';

export type ApiReconciliationStatus =
  | 'MATCHED'
  | 'WITHIN_ROUNDING_TOLERANCE'
  | 'VARIANCE_DETECTED'
  | 'PENDING_INPUT';

export type ApiLineItemReconciliationStatus =
  | 'NO_LINE_ITEMS'
  | 'MATCHED'
  | 'VARIANCE_WARNING';

export type FlagCategory =
  | 'ARITHMETIC_MISMATCH'
  | 'DUPLICATE_SUSPICION'
  | 'GSTIN_ISSUE'
  | 'HSN_RATE_MISMATCH'
  | 'MISSING_PO_GRN'
  | 'FIELD_DISCREPANCY'
  | 'CUSTOM';

export interface AuthenticatedUser {
  id: string;
  email: string;
  fullName: string;
  isActive: boolean;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  firmType: string;
  role: OrgRole;
}

export interface WorkspaceMembershipSummary {
  workspaceId: string;
  organizationId: string;
  name: string;
  workspaceCode: string;
  role: WorkspaceRole;
}

export interface ApiDiscrepancy {
  code: string;
  severity: 'info' | 'warning' | 'error' | 'INFO' | 'WARNING';
  message: string;
  details: Record<string, unknown>;
}

export interface ApiDuplicateMatch {
  invoiceId: string;
  invoiceNumber: string;
  invoiceDate: string | null;
  totalAmount: string;
  status: string;
  matchReasons: string[];
}

export interface ApiReviewFlag {
  id: string;
  workspaceId: string;
  invoiceId: string;
  flagCategory: FlagCategory | string;
  reasonText: string;
  status: 'OPEN' | 'RESOLVED' | 'DISMISSED';
  createdByUserId: string | null;
  createdByName: string | null;
  resolvedByUserId: string | null;
  resolvedByName: string | null;
  resolutionNote: string | null;
  createdAt: string;
  resolvedAt: string | null;
}

export interface ApiReviewAction {
  id: string;
  workspaceId: string;
  invoiceId: string;
  actorUserId: string | null;
  actorDisplayName: string;
  actionType: string;
  previousStatus: string;
  newStatus: string;
  varianceAcknowledged: boolean;
  varianceAmountAtAction: string | null;
  comment: string | null;
  fieldChanges: Record<string, unknown>;
  createdAt: string;
}

export interface ApiAuditEvent {
  id: string;
  organizationId: string;
  workspaceId: string | null;
  actorUserId: string | null;
  actorDisplayName: string;
  eventType: string;
  entityType: string;
  entityId: string | null;
  summary: string;
  tone: 'neutral' | 'success' | 'warning';
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface ApiReviewHistory {
  invoiceId: string;
  status: string;
  actions: ApiReviewAction[];
  flags: ApiReviewFlag[];
  auditEvents: ApiAuditEvent[];
  totalActions: number;
  totalFlags: number;
  totalAuditEvents: number;
  page: number;
  pageSize: number;
}

export interface ApiReportSummary {
  workspaceId: string;
  currency: string;
  dateFrom: string | null;
  dateTo: string | null;
  totalInvoices: number;
  pendingCount: number;
  verifiedCount: number;
  flaggedCount: number;
  verificationRatePercent: number;
  pendingValue: string;
  verifiedValue: string;
  flaggedValue: string;
  totalTaxableValue: string;
  totalCgst: string;
  totalSgst: string;
  totalIgst: string;
  totalCess: string;
  totalGst: string;
  totalInvoiceValue: string;
  openFlagCount: number;
  outstandingReviewCount: number;
  varianceInvoiceCount: number;
  isStatutoryFilingReport: boolean;
  disclaimer: string;
}

export interface ApiReportExceptionFlagSnippet {
  id: string;
  flagCategory: string;
  reasonText: string;
  createdByName: string | null;
  createdAt: string;
}

export interface ApiReportExceptionLastAction {
  id: string;
  actionType: string;
  actorDisplayName: string;
  comment: string | null;
  createdAt: string;
}

export interface ApiReportExceptionItem {
  invoiceId: string;
  workspaceId: string;
  supplierId: string | null;
  invoiceNumber: string;
  supplierName: string;
  supplierGstin: string | null;
  invoiceDate: string | null;
  uploadDate: string;
  currency: string;
  totalAmount: string;
  varianceAmount: string;
  lineItemVarianceAmount: string | null;
  status: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED';
  reconciliationStatus: ApiReconciliationStatus;
  lineItemReconciliationStatus: ApiLineItemReconciliationStatus;
  duplicateWarning: string | null;
  openFlagCount: number;
  openFlags: ApiReportExceptionFlagSnippet[];
  lastAction: ApiReportExceptionLastAction | null;
  updatedAt: string;
}

export interface Invoice {
  id: string;
  invoiceNumber: string;
  supplierId: string;
  supplierName: string;
  supplierGstin: string;
  invoiceDate: string;
  uploadDate: string;
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  totalAmount: number;
  status: InvoiceStatus;
  reviewerNote: string;
  flagReason?: string;
  duplicateWarning?: string;
  documentFileName: string;
  documentPageCount: number;
  localPreviewUrl?: string;
  localPreviewMimeType?: string;
  isLocalUpload?: boolean;
  lineItems: InvoiceLineItem[];
  fieldMeta: Record<InvoiceFieldKey, InvoiceFieldMeta>;
  currency?: string;
  cessAmount?: number;
  roundOffAmount?: number;
  discountAmount?: number;
  freightAmount?: number;
  otherChargesAmount?: number;
  dueDate?: string | null;
  documentId?: string | null;
  documentMimeType?: string | null;
  documentScanStatus?: DocumentScanStatus | null;
  computedExpectedTotal?: number;
  varianceAmount?: number;
  reconciliationStatus?: ApiReconciliationStatus;
  lineItemsTaxableSum?: number | null;
  lineItemVarianceAmount?: number | null;
  lineItemReconciliationStatus?: ApiLineItemReconciliationStatus;
  lineItemWarning?: string | null;
  reconciliationDiscrepancies?: ApiDiscrepancy[];
  duplicateMatches?: ApiDuplicateMatch[];
  reviewFlags?: ApiReviewFlag[];
  openFlagCount?: number;
  verifiedByUserId?: string | null;
  verifiedAt?: string | null;
  updatedAt?: string;
}

export interface Supplier {
  id: string;
  name: string;
  gstin: string;
  stateCode: string;
  stateName: string;
  category: string;
  status: SupplierStatus;
  email: string;
}

export interface SupplierSummary extends Supplier {
  totalInvoices: number;
  totalValue: number;
  lastInvoiceDate: string;
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  invoiceId?: string;
  invoiceNumber?: string;
  tone: 'neutral' | 'success' | 'warning';
}

export type NotificationCategory = 'flagged' | 'duplicate' | 'digest';

export interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  timeLabel: string;
  read: boolean;
  targetRoute: AppRoute;
  targetInvoiceId?: string;
  category?: NotificationCategory;
}

export interface WorkspaceSettings {
  workspaceName: string;
  firmType: string;
  workspaceCode: string;
  legalEntityName: string;
  companyGstin: string;
  companyPan: string;
  registeredAddress: string;
  requireHumanReview: true;
  enableDuplicateWarnings: boolean;
  autoFlagTaxMismatch: boolean;
  currency: 'INR';
  financialYear: 'April - March';
  dateFormat: 'DD/MM/YYYY';
  taxRegime: 'India GST (CGST / SGST / IGST)';
  notifyFlaggedInvoices: boolean;
  notifyDailyDigest: boolean;
  notifyDuplicateAlerts: boolean;
  roundingTolerance?: number;
  defaultCurrency?: string;
  updatedAt?: string;
}

export interface HistoricalMonthStat {
  monthKey: string;
  label: string;
  totalCount: number;
  verifiedCount: number;
  pendingCount: number;
  flaggedCount: number;
  totalValue: number;
  totalTaxableValue?: number;
  totalGst?: number;
}

export interface LocalUiPreferences {
  compactTables: boolean;
}

