import {
  ChevronLeft,
  ChevronRight,
  FileText,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { formatDateIN, formatINR } from '../../services/formatters';
import type { Invoice, InvoiceFieldKey } from '../../types/domain';

export function DocumentPreview({
  invoice,
  focusedField,
}: {
  invoice: Invoice;
  focusedField: InvoiceFieldKey | null;
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

  const isLocalPdf =
    invoice.isLocalUpload &&
    invoice.localPreviewUrl &&
    invoice.localPreviewMimeType === 'application/pdf';

  const isLocalImage =
    invoice.isLocalUpload &&
    invoice.localPreviewUrl &&
    invoice.localPreviewMimeType?.startsWith('image/');

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100/80">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-slate-500" />
          <span className="truncate font-mono text-xs font-medium text-slate-700">
            {invoice.documentFileName}
          </span>
        </div>

        <div className="flex items-center gap-3">
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
              Page {page} of {invoice.documentPageCount}
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
              onClick={() => setZoom((z) => Math.max(70, z - 15))}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white"
              aria-label="Zoom out"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <span className="w-10 text-center font-mono text-[11px] font-medium text-slate-700 tabular-nums">
              {zoom}%
            </span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(160, z + 15))}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white"
              aria-label="Zoom in"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setZoom(100)}
              className="flex h-8 w-8 items-center justify-center rounded text-slate-600 hover:bg-white"
              aria-label="Reset zoom"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 sm:p-6">
        {isLocalPdf ? (
          <iframe
            src={invoice.localPreviewUrl}
            title={invoice.documentFileName}
            className="h-[580px] w-full rounded-lg border border-slate-200 bg-white"
          />
        ) : isLocalImage ? (
          <div className="flex justify-center">
            <img
              src={invoice.localPreviewUrl}
              alt={invoice.documentFileName}
              style={{ width: `${zoom}%` }}
              className="max-w-none rounded-lg border border-slate-200 bg-white"
            />
          </div>
        ) : invoice.isLocalUpload ? (
          <div className="flex h-full min-h-[420px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <FileText className="h-10 w-10 text-slate-400" />
            <p className="mt-3 text-sm font-semibold text-slate-900">
              Local File Preview Expired Across Reload
            </p>
            <p className="mt-1 max-w-sm text-xs text-slate-500">
              Browser Object URLs are session-scoped. Re-upload a sample file via
              Invoices &rarr; Upload Invoice to preview it here.
            </p>
          </div>
        ) : (
          <div className="flex justify-center">
            <div
              style={{
                transform: `scale(${zoom / 100})`,
                transformOrigin: 'top center',
              }}
              className="w-full max-w-[600px] rounded-lg border border-slate-300 bg-white p-7 text-slate-800 shadow-sm"
            >
              {page === 1 ? (
                <div className="space-y-5 text-xs">
                  <div className="flex items-start justify-between border-b border-slate-200 pb-4">
                    <div className={highlightClass(['supplierName', 'supplierGstin'])}>
                      <p className="text-[11px] font-semibold text-slate-400">
                        Tax Invoice · Simulated Sample
                      </p>
                      <h3 className="mt-1 text-base font-bold text-slate-900">
                        {invoice.supplierName}
                      </h3>
                      <p className="mt-1 font-mono text-[11px] text-slate-600">
                        GSTIN: {invoice.supplierGstin}
                      </p>
                    </div>
                    <div
                      className={`text-right ${highlightClass([
                        'invoiceNumber',
                        'invoiceDate',
                      ])}`}
                    >
                      <p className="font-mono text-xs font-semibold text-slate-900">
                        {invoice.invoiceNumber}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-500 tabular-nums">
                        Date: {formatDateIN(invoice.invoiceDate)}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 rounded-md bg-slate-50 p-3 text-[11px]">
                    <div>
                      <p className="font-semibold text-slate-500">Billed To</p>
                      <p className="mt-0.5 font-medium text-slate-900">
                        Client Workspace Entity (Sample)
                      </p>
                      <p className="font-mono text-slate-500">GSTIN: 27AABCD1234E1Z5</p>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-500">Place of Supply</p>
                      <p className="mt-0.5 font-medium text-slate-900">
                        27 - Maharashtra
                      </p>
                      <p className="text-slate-500">
                        {invoice.igst > 0 ? 'Inter-State Supply' : 'Intra-State Supply'}
                      </p>
                    </div>
                  </div>

                  <table className="w-full border-collapse text-[11px]">
                    <thead>
                      <tr className="border-y border-slate-200 bg-slate-50 text-left text-slate-600">
                        <th className="py-2 pr-2 font-semibold">Description</th>
                        <th className="px-2 py-2 font-semibold">HSN/SAC</th>
                        <th className="px-2 py-2 text-right font-semibold">Qty</th>
                        <th className="py-2 pl-2 text-right font-semibold">Taxable</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {invoice.lineItems.map((item) => (
                        <tr key={item.id}>
                          <td className="py-2.5 pr-2 text-slate-800">{item.description}</td>
                          <td className="px-2 py-2.5 font-mono text-slate-500">
                            {item.hsnSac}
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
                      <div className={`flex justify-between ${highlightClass(['cgst'])}`}>
                        <span className="text-slate-500">CGST</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.cgst)}
                        </span>
                      </div>
                      <div className={`flex justify-between ${highlightClass(['sgst'])}`}>
                        <span className="text-slate-500">SGST</span>
                        <span className="font-mono tabular-nums">
                          {formatINR(invoice.sgst)}
                        </span>
                      </div>
                      <div className={`flex justify-between ${highlightClass(['igst'])}`}>
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
              ) : (
                <div className="space-y-4 py-6 text-xs">
                  <div className="border-b border-slate-200 pb-3">
                    <p className="text-[11px] font-semibold text-slate-400">
                      Annexure &amp; Declarations · Page 2
                    </p>
                    <p className="mt-1 font-semibold text-slate-900">
                      {invoice.invoiceNumber} — {invoice.supplierName}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-[11px] leading-relaxed text-slate-600">
                    <p className="font-semibold text-slate-800">
                      Simulated Supporting Terms &amp; Delivery Reference
                    </p>
                    <p className="mt-2">
                      1. E-Invoice IRN / QR block placeholder for Indian B2B GST
                      compliance.
                    </p>
                    <p className="mt-1">
                      2. Goods / services inspected at receiving location. Subject to
                      Chartered Accountant verification prior to ledger posting.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
