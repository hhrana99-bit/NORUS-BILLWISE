import type { Invoice, WorkspaceSettings } from '../types/domain';

const STORAGE_KEY_SETTINGS = 'norus_billwise_demo_settings_v1';
const STORAGE_KEY_INVOICES = 'norus_billwise_demo_invoices_v1';

export function loadStoredSettings(): WorkspaceSettings | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_SETTINGS);
    if (!raw) return null;
    return JSON.parse(raw) as WorkspaceSettings;
  } catch {
    return null;
  }
}

export function saveStoredSettings(settings: WorkspaceSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY_SETTINGS, JSON.stringify(settings));
  } catch {
    // Ignore storage quota or private browsing errors in prototype mode.
  }
}

export function loadStoredInvoices(): Invoice[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_INVOICES);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Invoice[];
    return parsed.map((inv) =>
      inv.isLocalUpload ? { ...inv, localPreviewUrl: undefined } : inv
    );
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
    localStorage.setItem(STORAGE_KEY_INVOICES, JSON.stringify(serializable));
  } catch {
    // Ignore storage quota errors in prototype mode.
  }
}

export function clearAllDemoStorage(): void {
  try {
    localStorage.removeItem(STORAGE_KEY_SETTINGS);
    localStorage.removeItem(STORAGE_KEY_INVOICES);
  } catch {
    // Ignore errors.
  }
}
