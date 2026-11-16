import type { Invoice } from '../types/domain';

export type RevokeObjectUrlFn = (url: string) => void;

const defaultRevokeObjectUrl: RevokeObjectUrlFn = (url: string) => {
  if (typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(url);
  }
};

export function isBlobObjectUrl(url: string | undefined): url is string {
  return typeof url === 'string' && url.startsWith('blob:');
}

export function revokeUnusedBlobUrls(
  prevInvoices: Invoice[],
  nextInvoices: Invoice[],
  revokeFn: RevokeObjectUrlFn = defaultRevokeObjectUrl
): string[] {
  const activeNextUrls = new Set<string>();
  for (const inv of nextInvoices) {
    if (isBlobObjectUrl(inv.localPreviewUrl)) {
      activeNextUrls.add(inv.localPreviewUrl);
    }
  }

  const revoked = new Set<string>();
  for (const inv of prevInvoices) {
    const url = inv.localPreviewUrl;
    if (isBlobObjectUrl(url) && !activeNextUrls.has(url) && !revoked.has(url)) {
      revokeFn(url);
      revoked.add(url);
    }
  }

  return [...revoked];
}

export function revokeAllBlobUrls(
  invoices: Invoice[],
  revokeFn: RevokeObjectUrlFn = defaultRevokeObjectUrl
): string[] {
  const revoked = new Set<string>();
  for (const inv of invoices) {
    const url = inv.localPreviewUrl;
    if (isBlobObjectUrl(url) && !revoked.has(url)) {
      revokeFn(url);
      revoked.add(url);
    }
  }
  return [...revoked];
}
