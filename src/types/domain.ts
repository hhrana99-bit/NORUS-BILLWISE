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

export interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  timeLabel: string;
  read: boolean;
  targetRoute: AppRoute;
  targetInvoiceId?: string;
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
}

export interface HistoricalMonthStat {
  monthKey: string;
  label: string;
  totalCount: number;
  verifiedCount: number;
  pendingCount: number;
  flaggedCount: number;
  totalValue: number;
}
