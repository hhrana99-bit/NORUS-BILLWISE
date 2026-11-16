import {
  AlertTriangle,
  CheckCircle2,
  Flag,
  Info,
  Save,
  ShieldAlert,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { DocumentPreview } from '../components/invoices/DocumentPreview';
import { formatINR } from '../services/formatters';
import { computeArithmeticCheck } from '../services/invoiceService';
import { useWorkspace } from '../state/WorkspaceContext';
import type {
  FieldVerificationStatus,
  Invoice,
  InvoiceFieldKey,
} from '../types/domain';

export function ReviewCentrePage() {
  const {
    invoices,
    selectedInvoiceId,
    selectInvoiceForReview,
    updateInvoice,
  } = useWorkspace();

  const currentInvoice =
    invoices.find((inv) => inv.id === selectedInvoiceId) ?? invoices[0];

  const [draft, setDraft] = useState<Invoice>(currentInvoice);
  const [focusedField, setFocusedField] = useState<InvoiceFieldKey | null>(null);
  const [feedbackBanner, setFeedbackBanner] = useState<string>('');
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (currentInvoice) {
      setDraft(currentInvoice);
      setDirty(false);
      setFeedbackBanner('');
    }
  }, [currentInvoice]);

  if (!draft) {
    return null;
  }

  const check = computeArithmeticCheck(draft);

  const updateTextField = (
    key: 'supplierName' | 'supplierGstin' | 'invoiceNumber' | 'invoiceDate',
    value: string
  ) => {
    setDirty(true);
    setDraft((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const updateNumericField = (
    key: 'taxableAmount' | 'cgst' | 'sgst' | 'igst' | 'totalAmount',
    rawValue: string
  ) => {
    const parsed = rawValue === '' ? 0 : Number(rawValue);
    if (Number.isNaN(parsed)) return;
    setDirty(true);
    setDraft((prev) => ({
      ...prev,
      [key]: parsed,
    }));
  };

  const setFieldStatus = (key: InvoiceFieldKey, status: FieldVerificationStatus) => {
    setDirty(true);
    setDraft((prev) => ({
      ...prev,
      fieldMeta: {
        ...prev.fieldMeta,
        [key]: {
          ...prev.fieldMeta[key],
          status,
        },
      },
    }));
  };

  const handleSaveChanges = () => {
    updateInvoice(draft, 'Saved manual edits in Review Centre');
    setDirty(false);
    setFeedbackBanner('Changes saved to local prototype state.');
  };

  const handleVerify = () => {
    const nextFieldMeta = { ...draft.fieldMeta };
    (Object.keys(nextFieldMeta) as InvoiceFieldKey[]).forEach((key) => {
      nextFieldMeta[key] = { ...nextFieldMeta[key], status: 'Verified' };
    });

    const verifiedInvoice: Invoice = {
      ...draft,
      status: 'Verified',
      flagReason: undefined,
      fieldMeta: nextFieldMeta,
    };
    setDraft(verifiedInvoice);
    updateInvoice(verifiedInvoice, 'Marked invoice as Verified after human review');
    setDirty(false);
    setFeedbackBanner('Invoice marked as Verified. Dashboard and Reports updated.');
  };

  const handleFlag = () => {
    const reason =
      draft.flagReason?.trim() ||
      (!check.isBalanced
        ? `Tax + taxable total mismatch of ${formatINR(Math.abs(check.difference))}`
        : 'Flagged by reviewer for secondary verification');

    const flaggedInvoice: Invoice = {
      ...draft,
      status: 'Flagged',
      flagReason: reason,
    };
    setDraft(flaggedInvoice);
    updateInvoice(flaggedInvoice, `Flagged invoice for review: ${reason}`);
    setDirty(false);
    setFeedbackBanner('Invoice flagged for review.');
  };

  const renderFieldStatusControl = (fieldKey: InvoiceFieldKey) => {
    const status = draft.fieldMeta[fieldKey].status;
    return (
      <select
        value={status}
        onChange={(e) =>
          setFieldStatus(fieldKey, e.target.value as FieldVerificationStatus)
        }
        aria-label={`Verification status for ${fieldKey}`}
        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium focus:outline-none ${
          status === 'Verified'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : status === 'Flagged'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-amber-200 bg-amber-50 text-amber-700'
        }`}
      >
        <option value="Verified">Verified</option>
        <option value="Needs Review">Needs Review</option>
        <option value="Flagged">Flagged</option>
      </select>
    );
  };

  const renderEvidenceLine = (fieldKey: InvoiceFieldKey) => (
    <p className="mt-1 text-[11px] text-slate-400">
      {draft.fieldMeta[fieldKey].evidenceNote}
    </p>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2.5 rounded-xl border border-indigo-200 bg-indigo-50/70 px-4 py-3 text-xs text-indigo-950">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
        <p>
          <strong>Frontend Prototype Notice:</strong> Field values shown here are
          mock accounting records (or locally staged files). Real OCR, bounding-box
          source evidence, and AI-assisted field suggestions will be integrated in a
          later development task. Human sign-off is always required.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-600">
            Active Document:
          </label>
          <select
            value={draft.id}
            onChange={(e) => selectInvoiceForReview(e.target.value)}
            aria-label="Select invoice to review"
            className="h-10 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-900 focus:border-indigo-500 focus:outline-none"
          >
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.invoiceNumber} — {inv.supplierName} ({inv.status})
              </option>
            ))}
          </select>
          <StatusBadge status={draft.status} />
          {dirty && (
            <span className="text-xs font-medium text-amber-600">
              Unsaved edits
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSaveChanges}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50 whitespace-nowrap"
          >
            <Save className="h-3.5 w-3.5" />
            Save Changes
          </button>
          <button
            type="button"
            onClick={handleFlag}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-4 text-xs font-semibold text-rose-700 hover:bg-rose-100 whitespace-nowrap"
          >
            <Flag className="h-3.5 w-3.5" />
            Flag for Review
          </button>
          <button
            type="button"
            onClick={handleVerify}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-emerald-600 px-4 text-xs font-semibold text-white hover:bg-emerald-700 whitespace-nowrap"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Mark as Verified
          </button>
        </div>
      </div>

      {feedbackBanner && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-800">
          {feedbackBanner}
        </div>
      )}

      {draft.duplicateWarning && (
        <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <span className="font-semibold">Duplicate Warning (Advisory Only): </span>
            <span>{draft.duplicateWarning}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-6 lg:h-[760px]">
          <DocumentPreview invoice={draft} focusedField={focusedField} />
        </div>

        <div className="space-y-5 lg:col-span-6">
          <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
            <div className="border-b border-slate-100 pb-3">
              <h2 className="text-sm font-semibold text-slate-900">
                Supplier &amp; Invoice Metadata
              </h2>
              <p className="text-xs text-slate-500">
                Focus any field to highlight the corresponding document block
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Supplier Name
                  </label>
                  {renderFieldStatusControl('supplierName')}
                </div>
                <input
                  type="text"
                  value={draft.supplierName}
                  onFocus={() => setFocusedField('supplierName')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateTextField('supplierName', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('supplierName')}
              </div>

              <div className="sm:col-span-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Supplier GSTIN
                  </label>
                  {renderFieldStatusControl('supplierGstin')}
                </div>
                <input
                  type="text"
                  value={draft.supplierGstin}
                  onFocus={() => setFocusedField('supplierGstin')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateTextField('supplierGstin', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('supplierGstin')}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Invoice Number
                  </label>
                  {renderFieldStatusControl('invoiceNumber')}
                </div>
                <input
                  type="text"
                  value={draft.invoiceNumber}
                  onFocus={() => setFocusedField('invoiceNumber')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateTextField('invoiceNumber', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('invoiceNumber')}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Invoice Date
                  </label>
                  {renderFieldStatusControl('invoiceDate')}
                </div>
                <input
                  type="date"
                  value={draft.invoiceDate}
                  onFocus={() => setFocusedField('invoiceDate')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateTextField('invoiceDate', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('invoiceDate')}
              </div>
            </div>
          </div>

          <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  Tax &amp; Amount Verification (INR)
                </h2>
                <p className="text-xs text-slate-500">
                  Live reconciliation check: Taxable + CGST + SGST + IGST
                </p>
              </div>
              {check.isBalanced ? (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  Totals Reconciled
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-rose-700 tabular-nums">
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-600" />
                  Variance: {formatINR(check.difference)}
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">
                    Taxable Amount (₹)
                  </label>
                  {renderFieldStatusControl('taxableAmount')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  value={draft.taxableAmount}
                  onFocus={() => setFocusedField('taxableAmount')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('taxableAmount', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('taxableAmount')}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">CGST (₹)</label>
                  {renderFieldStatusControl('cgst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  value={draft.cgst}
                  onFocus={() => setFocusedField('cgst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('cgst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('cgst')}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">SGST (₹)</label>
                  {renderFieldStatusControl('sgst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  value={draft.sgst}
                  onFocus={() => setFocusedField('sgst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('sgst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('sgst')}
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-slate-700">IGST (₹)</label>
                  {renderFieldStatusControl('igst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  value={draft.igst}
                  onFocus={() => setFocusedField('igst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('igst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
                {renderEvidenceLine('igst')}
              </div>

              <div className="sm:col-span-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-900">
                    Total Invoice Amount (₹)
                  </label>
                  {renderFieldStatusControl('totalAmount')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  value={draft.totalAmount}
                  onFocus={() => setFocusedField('totalAmount')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('totalAmount', e.target.value)}
                  className={`mt-1.5 h-10 w-full rounded-lg border px-3 font-mono text-sm font-semibold tabular-nums focus:outline-none focus:ring-2 ${
                    check.isBalanced
                      ? 'border-slate-200 text-slate-900 focus:border-indigo-500 focus:ring-indigo-500/15'
                      : 'border-rose-300 bg-rose-50/40 text-rose-900 focus:border-rose-500 focus:ring-rose-500/15'
                  }`}
                />
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <span className="text-slate-400">
                    {draft.fieldMeta.totalAmount.evidenceNote}
                  </span>
                  <span className="font-mono font-medium text-slate-600 tabular-nums">
                    Expected sum: {formatINR(check.expectedTotal)}
                  </span>
                </div>
              </div>
            </div>

            <div className="border-t border-slate-100 pt-3">
              <label className="block text-xs font-medium text-slate-700">
                Reviewer Note / Audit Remarks
              </label>
              <textarea
                rows={2}
                value={draft.reviewerNote}
                onChange={(e) => {
                  setDirty(true);
                  setDraft((prev) => ({ ...prev, reviewerNote: e.target.value }));
                }}
                placeholder="Add accounting or GST verification notes..."
                className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
            </div>

            {draft.status === 'Flagged' && draft.flagReason && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900">
                <strong>Flag Reason:</strong> {draft.flagReason}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
