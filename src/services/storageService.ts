import type {
  FieldVerificationStatus,
  Invoice,
  InvoiceFieldKey,
  InvoiceStatus,
  WorkspaceSettings,
} from '../types/domain';

export const STORAGE_SCHEMA_VERSION = 2;

const STORAGE_KEY_SETTINGS = 'norus_billwise_demo_settings_v2';
const STORAGE_KEY_INVOICES = 'norus_billwise_demo_invoices_v2';
const LEGACY_STORAGE_KEYS = [
  'norus_billwise_demo_settings_v1',
  'norus_billwise_demo_invoices_v1',
];

interface StorageEnvelope<T> {
  schemaVersion: number;
  data: T;
}

const REQUIRED_FIELD_KEYS: InvoiceFieldKey[] = [
  'supplierName',
  'supplierGstin',
  'invoiceNumber',
  'invoiceDate',
  'taxableAmount',
  'cgst',
  'sgst',
  'igst',
  'totalAmount',
];

const VALID_INVOICE_STATUSES: ReadonlySet<InvoiceStatus> = new Set([
  'Pending Review',
  'Verified',
  'Flagged',
]);

const VALID_FIELD_STATUSES: ReadonlySet<FieldVerificationStatus> = new Set([
  'Verified',
  'Needs Review',
  'Flagged',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyOrString(value: unknown): value is string {
  return typeof value === 'string';
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function isValidWorkspaceSettings(value: unknown): value is WorkspaceSettings {
  if (!isRecord(value)) return false;

  return (
    isNonEmptyOrString(value.workspaceName) &&
    isNonEmptyOrString(value.firmType) &&
    isNonEmptyOrString(value.workspaceCode) &&
    isNonEmptyOrString(value.legalEntityName) &&
    isNonEmptyOrString(value.companyGstin) &&
    isNonEmptyOrString(value.companyPan) &&
    isNonEmptyOrString(value.registeredAddress) &&
    value.requireHumanReview === true &&
    typeof value.enableDuplicateWarnings === 'boolean' &&
    typeof value.autoFlagTaxMismatch === 'boolean' &&
    value.currency === 'INR' &&
    value.financialYear === 'April - March' &&
    value.dateFormat === 'DD/MM/YYYY' &&
    value.taxRegime === 'India GST (CGST / SGST / IGST)' &&
    typeof value.notifyFlaggedInvoices === 'boolean' &&
    typeof value.notifyDailyDigest === 'boolean' &&
    typeof value.notifyDuplicateAlerts === 'boolean'
  );
}

export function isValidInvoice(value: unknown): value is Invoice {
  if (!isRecord(value)) return false;

  if (
    !isNonEmptyOrString(value.id) ||
    !value.id ||
    !isNonEmptyOrString(value.invoiceNumber) ||
    !isNonEmptyOrString(value.supplierId) ||
    !isNonEmptyOrString(value.supplierName) ||
    !isNonEmptyOrString(value.supplierGstin) ||
    !isNonEmptyOrString(value.invoiceDate) ||
    !isNonEmptyOrString(value.uploadDate) ||
    !isNonEmptyOrString(value.reviewerNote) ||
    !isNonEmptyOrString(value.documentFileName) ||
    !isFiniteNumber(value.taxableAmount) ||
    !isFiniteNumber(value.cgst) ||
    !isFiniteNumber(value.sgst) ||
    !isFiniteNumber(value.igst) ||
    !isFiniteNumber(value.totalAmount) ||
    !isFiniteNumber(value.documentPageCount) ||
    !VALID_INVOICE_STATUSES.has(value.status as InvoiceStatus) ||
    !Array.isArray(value.lineItems) ||
    !isRecord(value.fieldMeta)
  ) {
    return false;
  }

  for (const item of value.lineItems) {
    if (
      !isRecord(item) ||
      !isNonEmptyOrString(item.id) ||
      !isNonEmptyOrString(item.description) ||
      !isNonEmptyOrString(item.hsnSac) ||
      !isFiniteNumber(item.quantity) ||
      !isFiniteNumber(item.unitPrice) ||
      !isFiniteNumber(item.taxRatePercent) ||
      !isFiniteNumber(item.taxableValue)
    ) {
      return false;
    }
  }

  for (const key of REQUIRED_FIELD_KEYS) {
    const meta = value.fieldMeta[key];
    if (
      !isRecord(meta) ||
      !VALID_FIELD_STATUSES.has(meta.status as FieldVerificationStatus) ||
      !isNonEmptyOrString(meta.evidenceNote)
    ) {
      return false;
    }
  }

  return true;
}

export function parseStoredSettingsRaw(raw: string | null): WorkspaceSettings | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.schemaVersion !== STORAGE_SCHEMA_VERSION) {
      return null;
    }
    return isValidWorkspaceSettings(parsed.data) ? parsed.data : null;
  } catch {
    return null;
  }
}

export function parseStoredInvoicesRaw(raw: string | null): Invoice[] | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.schemaVersion !== STORAGE_SCHEMA_VERSION) {
      return null;
    }
    if (!Array.isArray(parsed.data) || !parsed.data.every(isValidInvoice)) {
      return null;
    }
    return parsed.data.map((inv) =>
      inv.isLocalUpload ? { ...inv, localPreviewUrl: undefined } : inv
    );
  } catch {
    return null;
  }
}

export function loadStoredSettings(): WorkspaceSettings | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SETTINGS);
    if (!raw) return null;
    const valid = parseStoredSettingsRaw(raw);
    if (!valid) {
      localStorage.removeItem(STORAGE_KEY_SETTINGS);
    }
    return valid;
  } catch {
    return null;
  }
}

export function saveStoredSettings(settings: WorkspaceSettings): void {
  try {
    const envelope: StorageEnvelope<WorkspaceSettings> = {
      schemaVersion: STORAGE_SCHEMA_VERSION,
      data: settings,
    };
    localStorage.setItem(STORAGE_KEY_SETTINGS, JSON.stringify(envelope));
  } catch {
    // Ignore storage quota or private browsing errors in prototype mode.
  }
}

export function loadStoredInvoices(): Invoice[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_INVOICES);
    if (!raw) return null;
    const valid = parseStoredInvoicesRaw(raw);
    if (!valid) {
      localStorage.removeItem(STORAGE_KEY_INVOICES);
    }
    return valid;
  } catch {
    return null;
  }
}

export function saveStoredInvoices(invoices: Invoice[]): void {
  try {
    const serializable = invoices.map((inv) => {
      if (!inv.isLocalUpload) return inv;
      const { localPreviewUrl: _omit, ...rest } = inv;
      return rest;
    });
    const envelope: StorageEnvelope<Invoice[]> = {
      schemaVersion: STORAGE_SCHEMA_VERSION,
      data: serializable,
    };
    localStorage.setItem(STORAGE_KEY_INVOICES, JSON.stringify(envelope));
  } catch {
    // Ignore storage quota errors in prototype mode.
  }
}

export function clearAllDemoStorage(): void {
  try {
    localStorage.removeItem(STORAGE_KEY_SETTINGS);
    localStorage.removeItem(STORAGE_KEY_INVOICES);
    for (const legacyKey of LEGACY_STORAGE_KEYS) {
      localStorage.removeItem(legacyKey);
    }
  } catch {
    // Ignore errors.
  }
}
