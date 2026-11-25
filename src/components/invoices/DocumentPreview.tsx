import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  RotateCcw,
  ShieldAlert,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import { formatDateIN, formatINR } from '../../services/formatters';
import type {
  Invoice,
  InvoiceFieldKey,
  WorkspaceSettings,
} from '../../types/domain';

const INDIA_GST_STATE_NAMES: Record<string, string> = {
  '07': 'Delhi',
  '24': 'Gujarat',
  '27': 'Maharashtra',
  '29': 'Karnataka',
  '33': 'Tamil Nadu',
  '36': 'Telangana',
};

function deriveBuyerPlaceOfSupply(gstin: string | undefined): string {
  const clean = gstin?.trim().toUpperCase() ?? '';
  if (clean.length < 2) return 'Not configured';
  const code = clean.slice(0, 2);
  if (!/^\d{2}$/.test(code)) return 'Not configured';
  const stateName = INDIA_GST_STATE_NAMES[code];
  return stateName ? `${code} - ${stateName}` : `State Code ${code}`;
}

export function DocumentPreview({
  workspaceId,
  invoice,
  focusedField,
  settings,
  isDemoMode = false,
}: {
  workspaceId?: string | null;
  invoice: Invoice;
  focusedField: InvoiceFieldKey | null;
  settings?: Pick<
    WorkspaceSettings,
    'legalEntityName' | 'companyGstin' | 'registeredAddress' | 'workspaceName'
  >;
  isDemoMode?: boolean;
}) {
  const [zoom, setZoom] = useState(100);
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
    setZoom(100);
  }, [invoice.id]);

  const highlightClass = (fields: InvoiceFieldKey[]) =>
    focusedField && fields.includes(focusedField)
      ? 'ring-2 ring-indigo-500 bg-indigo-50/70 rounded px-1.5 py-0.5 -mx-1.5 transition'
      : 'transition';

  const hasRemoteDocument =
    !isDemoMode && Boolean(workspaceId && invoice.documentId);
  const scanStatus = invoice.documentScanStatus ?? null;
  const isCleanRemoteDocument = hasRemoteDocument && scanStatus === 'CLEAN';

  const remotePreviewUrl =
    isCleanRemoteDocument && workspaceId && invoice.documentId
      ? apiClient.getDocumentContentUrl(workspaceId, invoice.documentId, false)
      : null;

  const remoteDownloadUrl =
    isCleanRemoteDocument && workspaceId && invoice.documentId
      ? apiClient.getDocumentContentUrl(workspaceId, invoice.documentId, true)
      : null;

  const isRemotePdf =
    Boolean(remotePreviewUrl) &&
    invoice.documentMimeType === 'application/pdf';
  const isRemoteImage =
    Boolean(remotePreviewUrl) &&
    Boolean(invoice.documentMimeType?.startsWith('image/'));

  const buyerName =
    settings?.legalEntityName.trim() ||
    settings?.workspaceName.trim() ||
    'Buyer Entity Not Configured';
  const buyerGstin = settings?.companyGstin.trim() || '';
  const buyerAddress = settings?.registeredAddress.trim() || '';
  const placeOfSupply = deriveBuyerPlaceOfSupply(buyerGstin);

  const scale = zoom / 100;
  const pdfFrameHeight = Math.round(520 * scale);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2.5 sm:px-4">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="truncate font-mono text-xs font-medium text-slate-700">
            {invoice.documentFileName}
          </span>
          {remoteDownloadUrl && (
            <a
              href={remoteDownloadUrl}
              download={invoice.documentFileName}
              className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
              title="Download clean source file"
            >
              <Download className="h-3 w-3" />
              Download
            </a>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-1.5 py-0.5">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white disabled:opacity-40"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="px-1.5 font-mono text-[11px] font-medium text-slate-600 tabular-nums whitespace-nowrap">
              Page {page} of {Math.max(1, invoice.documentPageCount)}
            </span>
            <button
              type="button"
              disabled={page >= invoice.documentPageCount}
              onClick={() =>
                setPage((p) => Math.min(invoice.documentPageCount, p + 1))
              }
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white disabled:opacity-40"
              aria-label="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-1.5 py-0.5">
            <button
              type="button"
              disabled={zoom <= 70}
              onClick={() => setZoom((z) => Math.max(70, z - 15))}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white disabled:opacity-40"
              aria-label="Zoom out"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <span
              aria-label={`Preview zoom ${zoom}%`}
              className="w-11 text-center font-mono text-[11px] font-medium text-slate-700 tabular-nums"
            >
              {zoom}%
            </span>
            <button
              type="button"
              disabled={zoom >= 160}
              onClick={() => setZoom((z) => Math.min(160, z + 15))}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white disabled:opacity-40"
              aria-label="Zoom in"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              disabled={zoom === 100}
              onClick={() => setZoom(100)}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white disabled:opacity-40"
              aria-label="Reset zoom to 100%"
              title="Reset zoom (100%)"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3 sm:p-5">
        {hasRemoteDocument && !isCleanRemoteDocument && (
          <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-950">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div>
              <p className="font-semibold">
                Source File Preview Unavailable (Scan Status:{' '}
                {scanStatus ?? 'PENDING'})
              </p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-amber-900">
                {scanStatus === 'INFECTED'
                  ? 'This uploaded document failed security scanning and is blocked from streaming.'
                  : scanStatus === 'SKIPPED_DEV'
                    ? 'Development scan mode is active without a CLEAN verdict, so inline file streaming is disabled. Review structured ledger values below.'
                    : 'File streaming is enabled only after security scanning marks the document CLEAN.'}
              </p>
            </div>
          </div>
        )}

        {isRemotePdf && remotePreviewUrl ? (
          <div className="min-w-full">
            <div
              style={{
                width: `${zoom}%`,
                height: `${pdfFrameHeight}px`,
              }}
              className="mx-auto min-w-[260px] transition-[width,height] duration-150"
            >
              <iframe
                key={`${invoice.id}-${zoom}`}
                src={remotePreviewUrl}
                sandbox="allow-same-origin"
                title={invoice.documentFileName}
                className="h-full w-full rounded-lg border border-slate-200 bg-white"
              />
            </div>
          </div>
        ) : isRemoteImage && remotePreviewUrl ? (
          <div className="flex justify-start sm:justify-center">
            <img
              src={remotePreviewUrl}
              alt={invoice.documentFileName}
              style={{ width: `${zoom}%` }}
              className="max-w-none rounded-lg border border-slate-200 bg-white"
            />
          </div>
        ) : (
          <div className="min-w-full">
            <div
              style={{
                width: `${Math.round(560 * scale)}px`,
              }}
              className="mx-auto max-w-none"
            >
              <div
                style={{
                  width: '560px',
                  transform: `scale(${scale})`,
                  transformOrigin: 'top left',
                }}
                className="rounded-lg border border-slate-300 bg-white p-6 text-slate-800 shadow-sm sm:p-7"
              >
                <div className="space-y-5 text-xs">
                  <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
                    <div
                      className={highlightClass([
                        'supplierName',
                        'supplierGstin',
                      ])}
                    >
                      <p className="text-[11px] font-semibold text-slate-400">
                        {isDemoMode
                          ? 'Sample Document Preview'
                          : hasRemoteDocument
                            ? 'Structured Invoice Record'
                            : 'Manual Accounting Entry'}
                      </p>
                      <h3 className="mt-1 text-base font-bold text-slate-900">
                        {invoice.supplierName || 'Supplier Pending Entry'}
                      </h3>
                      <p className="mt-1 font-mono text-[11px] text-slate-600">
                        GSTIN: {invoice.supplierGstin || 'Not provided'}
                      </p>
                    </div>
                    <div
                      className={`shrink-0 text-right ${highlightClass([
                        'invoiceNumber',
                        'invoiceDate',
                      ])}`}
                    >
                      <p className="font-mono text-xs font-semibold text-slate-900">
                        {invoice.invoiceNumber}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500 tabular-nums">
                        Date:{' '}
                        {invoice.invoiceDate
                          ? formatDateIN(invoice.invoiceDate)
                          : 'Not entered'}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 rounded-md bg-slate-50 p-3 text-[11px]">
                    <div>
                      <p className="font-semibold text-slate-500">Billed To</p>
                      <p className="mt-0.5 font-medium text-slate-900">
                        {buyerName}
                      </p>
                      <p className="font-mono text-slate-500">
                        {buyerGstin
                          ? `GSTIN: ${buyerGstin}`
                          : 'GSTIN: Not configured'}
                      </p>
                      {buyerAddress && (
                        <p className="mt-0.5 text-[10px] text-slate-500">
                          {buyerAddress}
                        </p>
                      )}
                    </div>
                    <div>
                      <p className="font-semibold text-slate-500">
                        Place of Supply
                      </p>
                      <p className="mt-0.5 font-medium text-slate-900">
                        {placeOfSupply}
                      </p>
                      <p className="text-slate-500">
                        {invoice.igst > 0
                          ? 'Inter-State Supply'
                          : 'Intra-State Supply'}
                      </p>
                    </div>
                  </div>

                  {invoice.lineItems.length > 0 ? (
                    <table className="w-full border-collapse text-[11px]">
                      <thead>
                        <tr className="border-y border-slate-200 bg-slate-50 text-left text-slate-600">
                          <th className="py-2 pr-2 font-semibold">
                            Description
                          </th>
                          <th className="px-2 py-2 font-semibold">HSN/SAC</th>
                          <th className="px-2 py-2 text-right font-semibold">
                            Qty
                          </th>
                          <th className="py-2 pl-2 text-right font-semibold">
                            Taxable
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {invoice.lineItems.map((item) => (
                          <tr key={item.id}>
                            <td className="py-2.5 pr-2 text-slate-800">
                              {item.description}
                            </td>
                            <td className="px-2 py-2.5 font-mono text-slate-500">
                              {item.hsnSac || '—'}
                            </td>
                            <td className="px-2 py-2.5 text-right font-mono tabular-nums">
                              {item.quantity}
                            </td>
                            <td className="py-2.5 pl-2 text-right font-mono font-medium tabular-nums">
                              {formatINR(item.taxableValue)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-center text-[11px] text-slate-500">
                      No line items recorded on this invoice.
                    </p>
                  )}

                  <div className="flex justify-end border-t border-slate-200 pt-4">
                    <div className="w-64 space-y-1.5 text-[11px]">
                      <div
                        className={`flex justify-between ${highlightClass([
                          'taxableAmount',
                        ])}`}
                      >
                        <span className="text-slate-500">Taxable Value</span>
                        <span className="font-mono font-medium tabular-nums">
                          {formatINR(invoice.taxableAmount)}
                        </span>
                      </div>
                      <div
                        className={`flex justify-between ${highlightClass([
                          'cgst',
                        ])}`}
                      >
                        <span className="text-slate-500">CGST</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.cgst)}
                        </span>
                      </div>
                      <div
                        className={`flex justify-between ${highlightClass([
                          'sgst',
                        ])}`}
                      >
                        <span className="text-slate-500">SGST</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.sgst)}
                        </span>
                      </div>
                      <div
                        className={`flex justify-between ${highlightClass([
                          'igst',
                        ])}`}
                      >
                        <span className="text-slate-500">IGST</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.igst)}
                        </span>
                      </div>
                      <div
                        className={`flex justify-between border-t border-slate-200 pt-2 text-xs font-bold text-slate-900 ${highlightClass(
                          ['totalAmount']
                        )}`}
                      >
                        <span>Invoice Total</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.totalAmount)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
