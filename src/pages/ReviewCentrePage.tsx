import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Flag,
  History,
  Lock,
  RotateCcw,
  Save,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { EmptyState } from '../components/common/EmptyState';
import { DocumentPreview } from '../components/invoices/DocumentPreview';
import { FlagInvoiceModal } from '../components/invoices/FlagInvoiceModal';
import { formatApiErrorMessage } from '../services/apiClient';
import { formatDateIN, formatINR } from '../services/formatters';
import {
  computeArithmeticCheck,
  hasUnsavedInvoiceChanges,
} from '../services/invoiceService';
import { useWorkspace } from '../state/WorkspaceContext';
import type {
  ApiReviewFlag,
  FieldVerificationStatus,
  FlagCategory,
  Invoice,
  InvoiceFieldKey,
} from '../types/domain';

export function ReviewCentrePage() {
  const {
    activeWorkspaceId,
    activeWorkspaceRole,
    invoices,
    settings,
    selectedInvoiceId,
    selectedInvoiceDetail,
    selectedReviewHistory,
    detailLoading,
    detailError,
    mutationInFlight,
    selectInvoiceForReview,
    refreshSelectedInvoiceDetail,
    setHasUnsavedReviewChanges,
    pendingNavigation,
    cancelPendingNavigation,
    commitPendingNavigation,
    saveInvoiceChanges,
    verifyInvoiceAction,
    flagInvoiceAction,
    resolveFlagAction,
    reopenInvoiceAction,
    deleteInvoiceAction,
    navigate,
  } = useWorkspace();

  const currentInvoice =
    selectedInvoiceDetail ??
    invoices.find((inv) => inv.id === selectedInvoiceId) ??
    invoices[0];

  const [draftState, setDraft] = useState<Invoice | undefined>(currentInvoice);
  const [focusedField, setFocusedField] = useState<InvoiceFieldKey | null>(
    null
  );
  const [feedbackBanner, setFeedbackBanner] = useState<string>('');
  const [actionError, setActionError] = useState<string | null>(null);

  const [flagModalOpen, setFlagModalOpen] = useState(false);
  const [verifyDialogOpen, setVerifyDialogOpen] = useState(false);
  const [verifyAckVariance, setVerifyAckVariance] = useState(false);
  const [verifyNote, setVerifyNote] = useState('');
  const [verifyResolveOpenFlags, setVerifyResolveOpenFlags] = useState(false);
  const [verifyFlagNote, setVerifyFlagNote] = useState('');

  const [resolvingFlag, setResolvingFlag] = useState<ApiReviewFlag | null>(null);
  const [resolveStatus, setResolveStatus] = useState<'RESOLVED' | 'DISMISSED'>(
    'RESOLVED'
  );
  const [resolveNote, setResolveNote] = useState('');
  const [resolveReopenToPending, setResolveReopenToPending] = useState(true);

  const [reopenDialogOpen, setReopenDialogOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const prevInvoiceIdRef = useRef<string | undefined>(currentInvoice?.id);

  const draft =
    draftState && currentInvoice && draftState.id === currentInvoice.id
      ? draftState
      : currentInvoice;

  useEffect(() => {
    const prevId = prevInvoiceIdRef.current;
    const nextId = currentInvoice?.id;
    setDraft(currentInvoice);

    if (prevId !== nextId) {
      prevInvoiceIdRef.current = nextId;
      setFeedbackBanner('');
      setActionError(null);
      setFlagModalOpen(false);
      setVerifyDialogOpen(false);
      setResolvingFlag(null);
      setReopenDialogOpen(false);
      setDeleteDialogOpen(false);
    }
  }, [currentInvoice]);

  const hasUnsavedChanges = hasUnsavedInvoiceChanges(currentInvoice, draft);

  useEffect(() => {
    setHasUnsavedReviewChanges(hasUnsavedChanges);
  }, [hasUnsavedChanges, setHasUnsavedReviewChanges]);

  useEffect(() => {
    return () => {
      setHasUnsavedReviewChanges(false);
    };
  }, [setHasUnsavedReviewChanges]);

  useEffect(() => {
    if (!hasUnsavedChanges) return;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  if (detailLoading && !draft) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-500">
        Loading invoice review workspace...
      </div>
    );
  }

  if (!draft) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white">
        <EmptyState
          icon={<FileText className="h-5 w-5" />}
          title="No invoices available to review"
          description="Upload a PDF or image invoice or create a manual entry in the Invoices register."
          action={
            <button
              type="button"
              onClick={() => navigate('invoices')}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
            >
              Go to Invoices
            </button>
          }
        />
      </div>
    );
  }

  const isReviewerOrAdmin =
    activeWorkspaceRole === 'WORKSPACE_ADMIN' ||
    activeWorkspaceRole === 'REVIEWER';
  const isWorkspaceAdmin = activeWorkspaceRole === 'WORKSPACE_ADMIN';
  const isUploader = activeWorkspaceRole === 'UPLOADER';
  const isViewer = activeWorkspaceRole === 'VIEWER';

  const isVerifiedLocked = draft.status === 'Verified';
  const isUploaderFlagLocked = isUploader && draft.status === 'Flagged';
  const canEditFields = !isViewer && !isVerifiedLocked && !isUploaderFlagLocked;

  const check = computeArithmeticCheck(draft);
  const openFlags = (draft.reviewFlags ?? []).filter(
    (f) => f.status === 'OPEN'
  );
  const hasServerVariance =
    draft.reconciliationStatus === 'VARIANCE_DETECTED' || !check.isBalanced;
  const activeDuplicateWarning = settings.enableDuplicateWarnings
    ? draft.duplicateWarning
    : undefined;

  const canReopen =
    isReviewerOrAdmin &&
    (draft.status === 'Verified' ||
      (draft.status === 'Flagged' && openFlags.length === 0));

  const updateTextField = (
    key: 'supplierName' | 'supplierGstin' | 'invoiceNumber' | 'invoiceDate',
    value: string
  ) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            [key]: value,
          }
        : prev
    );
  };

  const updateNumericField = (
    key: 'taxableAmount' | 'cgst' | 'sgst' | 'igst' | 'totalAmount',
    rawValue: string
  ) => {
    const parsed = rawValue === '' ? 0 : Number(rawValue);
    if (Number.isNaN(parsed)) return;
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            [key]: parsed,
          }
        : prev
    );
  };

  const setFieldStatus = (
    key: InvoiceFieldKey,
    status: FieldVerificationStatus
  ) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            fieldMeta: {
              ...prev.fieldMeta,
              [key]: {
                ...prev.fieldMeta[key],
                status,
              },
            },
          }
        : prev
    );
  };

  const handleSaveChanges = async () => {
    if (!currentInvoice || !canEditFields) return;
    setActionError(null);
    setFeedbackBanner('');
    try {
      await saveInvoiceChanges(currentInvoice, draft);
      setFeedbackBanner('Changes saved to database.');
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const openVerifyModal = () => {
    setActionError(null);
    setVerifyAckVariance(false);
    setVerifyNote('');
    setVerifyResolveOpenFlags(openFlags.length > 0);
    setVerifyFlagNote('');
    setVerifyDialogOpen(true);
  };

  const handleVerifySubmit = async () => {
    if (!currentInvoice || !isReviewerOrAdmin) return;
    setActionError(null);
    setFeedbackBanner('');

    if (hasServerVariance && !verifyAckVariance) {
      setActionError(
        'Acknowledge the reconciliation variance before verifying this invoice.'
      );
      return;
    }
    if (openFlags.length > 0 && !verifyResolveOpenFlags) {
      setActionError(
        'Resolve open flags before verifying, or enable "Resolve open flags during verification".'
      );
      return;
    }
    if (openFlags.length > 0 && verifyResolveOpenFlags && !verifyFlagNote.trim()) {
      setActionError('Provide a flag resolution note to resolve open flags.');
      return;
    }

    try {
      if (hasUnsavedChanges) {
        await saveInvoiceChanges(currentInvoice, draft);
      }
      await verifyInvoiceAction(draft.id, {
        confirmVarianceAcknowledgment: hasServerVariance
          ? verifyAckVariance
          : false,
        confirmationNote: verifyNote.trim(),
        resolveOpenFlags: openFlags.length > 0 ? verifyResolveOpenFlags : false,
        flagResolutionNote:
          openFlags.length > 0 && verifyResolveOpenFlags
            ? verifyFlagNote.trim()
            : undefined,
      });
      setVerifyDialogOpen(false);
      setFeedbackBanner(
        'Invoice marked as Verified after human review. Record is now locked for audit integrity.'
      );
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const handleConfirmFlag = async (
    flagCategory: FlagCategory,
    reasonText: string
  ) => {
    if (!currentInvoice || !isReviewerOrAdmin) return;
    setActionError(null);
    setFeedbackBanner('');
    try {
      if (hasUnsavedChanges) {
        await saveInvoiceChanges(currentInvoice, draft);
      }
      await flagInvoiceAction(draft.id, { flagCategory, reasonText });
      setFlagModalOpen(false);
      setFeedbackBanner('Invoice flagged and held for secondary review.');
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const handleResolveFlagSubmit = async () => {
    if (!resolvingFlag || !isReviewerOrAdmin) return;
    if (!resolveNote.trim()) {
      setActionError('Resolution note is required.');
      return;
    }
    setActionError(null);
    setFeedbackBanner('');
    try {
      await resolveFlagAction(resolvingFlag.id, {
        resolutionStatus: resolveStatus,
        resolutionNote: resolveNote.trim(),
        reopenToPending: resolveReopenToPending,
      });
      setResolvingFlag(null);
      setResolveNote('');
      setFeedbackBanner(`Flag ${resolveStatus.toLowerCase()} cleanly.`);
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const handleReopenSubmit = async () => {
    if (!isReviewerOrAdmin) return;
    if (!reopenReason.trim()) {
      setActionError('Enter a reason to reopen this invoice to Pending Review.');
      return;
    }
    setActionError(null);
    setFeedbackBanner('');
    try {
      await reopenInvoiceAction(draft.id, reopenReason.trim());
      setReopenDialogOpen(false);
      setReopenReason('');
      setFeedbackBanner('Invoice reopened to Pending Review.');
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const handleConfirmDelete = async () => {
    if (!isWorkspaceAdmin) return;
    const deletedNumber = draft.invoiceNumber;
    setDeleteDialogOpen(false);
    setActionError(null);
    try {
      await deleteInvoiceAction(draft.id, 'Deleted from Review Centre');
      setFeedbackBanner(`Invoice ${deletedNumber} was soft-deleted.`);
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const renderFieldStatusControl = (fieldKey: InvoiceFieldKey) => {
    const status = draft.fieldMeta[fieldKey].status;
    return (
      <select
        disabled={!canEditFields}
        value={status}
        onChange={(e) =>
          setFieldStatus(fieldKey, e.target.value as FieldVerificationStatus)
        }
        aria-label={`Verification status for ${fieldKey}`}
        className={`rounded-md border px-2 py-0.5 text-[11px] font-medium focus:outline-none disabled:cursor-not-allowed disabled:opacity-70 ${
          status === 'Verified'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
            : status === 'Flagged'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-amber-200 bg-amber-50 text-amber-700'
        }`}
      >
        {!isUploader && <option value="Verified">Verified</option>}
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
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2.5 sm:gap-3">
          <label
            htmlFor="active-review-document-select"
            className="text-xs font-medium text-slate-600 whitespace-nowrap"
          >
            Active Document:
          </label>
          <select
            id="active-review-document-select"
            value={draft.id}
            onChange={(e) => selectInvoiceForReview(e.target.value)}
            aria-label="Select invoice to review"
            className="h-10 w-full min-w-0 max-w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-900 focus:border-indigo-500 focus:outline-none sm:w-auto sm:max-w-md"
          >
            {invoices.map((inv) => (
              <option key={inv.id} value={inv.id}>
                {inv.invoiceNumber} — {inv.supplierName} ({inv.status})
              </option>
            ))}
          </select>
          <StatusBadge status={draft.status} />
          {hasUnsavedChanges && (
            <span className="text-xs font-medium text-amber-600 whitespace-nowrap">
              Unsaved edits
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {isWorkspaceAdmin && draft.status !== 'Verified' && (
            <button
              type="button"
              disabled={mutationInFlight}
              onClick={() => setDeleteDialogOpen(true)}
              aria-label={`Soft-delete invoice ${draft.invoiceNumber}`}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-rose-600 hover:border-rose-200 hover:bg-rose-50 whitespace-nowrap disabled:opacity-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          )}
          {canEditFields && (
            <button
              type="button"
              disabled={mutationInFlight || !hasUnsavedChanges}
              onClick={() => void handleSaveChanges()}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              Save Changes
            </button>
          )}
          {canReopen && (
            <button
              type="button"
              disabled={mutationInFlight}
              onClick={() => {
                setActionError(null);
                setReopenReason('');
                setReopenDialogOpen(true);
              }}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-4 text-xs font-semibold text-amber-800 hover:bg-amber-100 whitespace-nowrap disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reopen
            </button>
          )}
          {isReviewerOrAdmin && (
            <>
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => {
                  setActionError(null);
                  setFlagModalOpen(true);
                }}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-4 text-xs font-semibold text-rose-700 hover:bg-rose-100 whitespace-nowrap disabled:opacity-50"
              >
                <Flag className="h-3.5 w-3.5" />
                Flag for Review
              </button>
              {!isVerifiedLocked && (
                <button
                  type="button"
                  disabled={mutationInFlight}
                  onClick={openVerifyModal}
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-emerald-600 px-4 text-xs font-semibold text-white hover:bg-emerald-700 whitespace-nowrap disabled:opacity-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Mark as Verified
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {isVerifiedLocked && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-2.5 text-xs text-emerald-950">
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 shrink-0 text-emerald-600" />
            <span>
              <strong>Verified Record Locked:</strong> Accounting fields are
              read-only after human sign-off.{' '}
              {draft.verifiedAt
                ? `Verified on ${new Date(draft.verifiedAt).toLocaleString('en-IN')}.`
                : ''}
            </span>
          </div>
        </div>
      )}

      {(isViewer || isUploaderFlagLocked) && (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
          <Lock className="h-4 w-4 shrink-0 text-slate-500" />
          <span>
            {isViewer
              ? 'Read-only access: your Viewer role cannot edit invoice fields or perform sign-off.'
              : 'Flagged invoice locked for Uploader role until a Reviewer resolves or reopens it.'}
          </span>
        </div>
      )}

      {(detailError || actionError) && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs font-medium text-rose-800"
        >
          <span>{actionError ?? detailError}</span>
          {detailError && (
            <button
              type="button"
              onClick={() => void refreshSelectedInvoiceDetail()}
              className="rounded border border-rose-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-rose-800"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {feedbackBanner && (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-800"
        >
          {feedbackBanner}
        </div>
      )}

      {activeDuplicateWarning && (
        <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <span className="font-semibold">
              Duplicate Warning (Advisory Only):{' '}
            </span>
            <span>{activeDuplicateWarning}</span>
            {draft.duplicateMatches && draft.duplicateMatches.length > 0 && (
              <ul className="mt-1 list-disc pl-4 text-[11px] text-amber-900">
                {draft.duplicateMatches.map((match) => (
                  <li key={match.invoiceId}>
                    <button
                      type="button"
                      onClick={() => selectInvoiceForReview(match.invoiceId)}
                      className="font-mono font-semibold underline"
                    >
                      {match.invoiceNumber}
                    </button>{' '}
                    ({match.status}) — {match.matchReasons.join(', ')}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="h-[480px] sm:h-[580px] lg:col-span-6 lg:h-[780px]">
          <DocumentPreview
            workspaceId={activeWorkspaceId}
            invoice={draft}
            focusedField={focusedField}
            settings={settings}
          />
        </div>

        <div className="space-y-5 lg:col-span-6">
          <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
            <div className="border-b border-slate-100 pb-3">
              <h2 className="text-sm font-semibold text-slate-900">
                Supplier &amp; Invoice Metadata
              </h2>
              <p className="text-xs text-slate-500">
                Verify supplier identity, GSTIN, and invoice metadata against
                the source document
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    Supplier Name
                  </label>
                  {renderFieldStatusControl('supplierName')}
                </div>
                <input
                  type="text"
                  disabled={!canEditFields}
                  value={draft.supplierName}
                  onFocus={() => setFocusedField('supplierName')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateTextField('supplierName', e.target.value)
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('supplierName')}
              </div>

              <div className="sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    Supplier GSTIN
                  </label>
                  {renderFieldStatusControl('supplierGstin')}
                </div>
                <input
                  type="text"
                  disabled={!canEditFields}
                  value={draft.supplierGstin}
                  onFocus={() => setFocusedField('supplierGstin')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateTextField('supplierGstin', e.target.value)
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('supplierGstin')}
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    Invoice Number
                  </label>
                  {renderFieldStatusControl('invoiceNumber')}
                </div>
                <input
                  type="text"
                  disabled={!canEditFields}
                  value={draft.invoiceNumber}
                  onFocus={() => setFocusedField('invoiceNumber')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateTextField('invoiceNumber', e.target.value)
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('invoiceNumber')}
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    Invoice Date
                  </label>
                  {renderFieldStatusControl('invoiceDate')}
                </div>
                <input
                  type="date"
                  disabled={!canEditFields}
                  value={draft.invoiceDate}
                  onFocus={() => setFocusedField('invoiceDate')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateTextField('invoiceDate', e.target.value)
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('invoiceDate')}
              </div>
            </div>
          </div>

          <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-sm font-semibold text-slate-900">
                  Tax &amp; Amount Reconciliation (INR)
                </h2>
                <p className="text-xs text-slate-500">
                  Server &amp; live check: Taxable + CGST + SGST + IGST
                </p>
              </div>
              {!settings.autoFlagTaxMismatch && !hasServerVariance ? (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                  Totals Reconciled
                </span>
              ) : !hasServerVariance ? (
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

            {draft.reconciliationDiscrepancies &&
              draft.reconciliationDiscrepancies.length > 0 && (
                <div className="space-y-1.5 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-950">
                  {draft.reconciliationDiscrepancies.map((d) => (
                    <p key={d.code}>
                      <strong className="font-mono">{d.code}:</strong>{' '}
                      {d.message}
                    </p>
                  ))}
                </div>
              )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    Taxable Amount (₹)
                  </label>
                  {renderFieldStatusControl('taxableAmount')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  disabled={!canEditFields}
                  value={draft.taxableAmount}
                  onFocus={() => setFocusedField('taxableAmount')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateNumericField('taxableAmount', e.target.value)
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('taxableAmount')}
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    CGST (₹)
                  </label>
                  {renderFieldStatusControl('cgst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  disabled={!canEditFields}
                  value={draft.cgst}
                  onFocus={() => setFocusedField('cgst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('cgst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('cgst')}
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    SGST (₹)
                  </label>
                  {renderFieldStatusControl('sgst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  disabled={!canEditFields}
                  value={draft.sgst}
                  onFocus={() => setFocusedField('sgst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('sgst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('sgst')}
              </div>

              <div>
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-medium text-slate-700">
                    IGST (₹)
                  </label>
                  {renderFieldStatusControl('igst')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  disabled={!canEditFields}
                  value={draft.igst}
                  onFocus={() => setFocusedField('igst')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) => updateNumericField('igst', e.target.value)}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-xs tabular-nums text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
                />
                {renderEvidenceLine('igst')}
              </div>

              <div className="sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-xs font-semibold text-slate-900">
                    Total Invoice Amount (₹)
                  </label>
                  {renderFieldStatusControl('totalAmount')}
                </div>
                <input
                  type="number"
                  step="0.01"
                  disabled={!canEditFields}
                  value={draft.totalAmount}
                  onFocus={() => setFocusedField('totalAmount')}
                  onBlur={() => setFocusedField(null)}
                  onChange={(e) =>
                    updateNumericField('totalAmount', e.target.value)
                  }
                  className={`mt-1.5 h-10 w-full rounded-lg border px-3 font-mono text-sm font-semibold tabular-nums focus:outline-none focus:ring-2 disabled:bg-slate-50 ${
                    !settings.autoFlagTaxMismatch || check.isBalanced
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
                disabled={!canEditFields}
                value={draft.reviewerNote}
                onChange={(e) =>
                  setDraft((prev) =>
                    prev ? { ...prev, reviewerNote: e.target.value } : prev
                  )
                }
                placeholder="Add accounting or GST verification notes..."
                className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15 disabled:bg-slate-50"
              />
            </div>

            {openFlags.length > 0 && (
              <div className="space-y-2 border-t border-slate-100 pt-3">
                <p className="text-xs font-semibold text-rose-800">
                  Open Review Flags ({openFlags.length})
                </p>
                {openFlags.map((flag) => (
                  <div
                    key={flag.id}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-950"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-[11px] font-semibold text-rose-700">
                        {flag.flagCategory}
                      </p>
                      <p className="mt-0.5">{flag.reasonText}</p>
                      <p className="mt-1 text-[11px] text-rose-700/80">
                        Raised {formatDateIN(flag.createdAt.slice(0, 10))}
                        {flag.createdByName ? ` by ${flag.createdByName}` : ''}
                      </p>
                    </div>
                    {isReviewerOrAdmin && (
                      <button
                        type="button"
                        onClick={() => {
                          setActionError(null);
                          setResolvingFlag(flag);
                          setResolveStatus('RESOLVED');
                          setResolveNote('');
                          setResolveReopenToPending(true);
                        }}
                        className="shrink-0 rounded-md border border-rose-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-rose-800 hover:bg-rose-100"
                      >
                        Resolve / Dismiss
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
            <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
              <History className="h-4 w-4 text-slate-500" />
              <h2 className="text-sm font-semibold text-slate-900">
                Immutable Review History
              </h2>
            </div>
            {!selectedReviewHistory ||
            selectedReviewHistory.actions.length === 0 ? (
              <p className="py-4 text-xs text-slate-500">
                No formal review actions logged for this invoice yet.
              </p>
            ) : (
              <div className="divide-y divide-slate-100">
                {selectedReviewHistory.actions.map((act) => (
                  <div key={act.id} className="py-3 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900">
                        {act.actorDisplayName} ·{' '}
                        <span className="font-mono text-[11px] text-indigo-700">
                          {act.actionType}
                        </span>
                      </span>
                      <span className="font-mono text-[11px] text-slate-400">
                        {new Date(act.createdAt).toLocaleString('en-IN')}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {act.previousStatus} &rarr; {act.newStatus}
                      {act.varianceAcknowledged
                        ? ' · Variance acknowledged by human reviewer'
                        : ''}
                    </p>
                    {act.comment && (
                      <p className="mt-1 text-slate-700">{act.comment}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <FlagInvoiceModal
        open={flagModalOpen}
        invoiceNumber={draft.invoiceNumber}
        initialReason={draft.flagReason}
        hasArithmeticMismatch={hasServerVariance}
        hasDuplicateWarning={Boolean(activeDuplicateWarning)}
        submitting={mutationInFlight}
        apiError={actionError}
        onConfirm={(cat, reason) => void handleConfirmFlag(cat, reason)}
        onClose={() => setFlagModalOpen(false)}
      />

      {verifyDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="verify-dialog-title"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
            <h3
              id="verify-dialog-title"
              className="text-sm font-semibold text-slate-900"
            >
              Confirm Human Invoice Verification
            </h3>
            <p className="mt-1 text-xs text-slate-600">
              Verifying{' '}
              <span className="font-mono font-semibold">
                {draft.invoiceNumber}
              </span>{' '}
              records an immutable reviewer sign-off and locks financial fields.
            </p>

            {hasServerVariance && (
              <div className="mt-3 space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
                <p className="font-semibold text-rose-700">
                  Arithmetic / Reconciliation Variance Detected:{' '}
                  {formatINR(check.difference)}
                </p>
                <label className="flex cursor-pointer items-start gap-2">
                  <input
                    type="checkbox"
                    checked={verifyAckVariance}
                    onChange={(e) => setVerifyAckVariance(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600"
                  />
                  <span>
                    I explicitly acknowledge this variance and confirm the
                    stated amounts should be verified as entered.
                  </span>
                </label>
              </div>
            )}

            {openFlags.length > 0 && (
              <div className="mt-3 space-y-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-950">
                <label className="flex cursor-pointer items-start gap-2 font-medium">
                  <input
                    type="checkbox"
                    checked={verifyResolveOpenFlags}
                    onChange={(e) =>
                      setVerifyResolveOpenFlags(e.target.checked)
                    }
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600"
                  />
                  <span>
                    Resolve {openFlags.length} open review flag(s) upon
                    verification
                  </span>
                </label>
                {verifyResolveOpenFlags && (
                  <input
                    type="text"
                    value={verifyFlagNote}
                    onChange={(e) => setVerifyFlagNote(e.target.value)}
                    placeholder="Flag resolution note (required)"
                    className="h-9 w-full rounded-lg border border-rose-200 bg-white px-2.5 text-xs"
                  />
                )}
              </div>
            )}

            <div className="mt-3">
              <label className="block text-xs font-medium text-slate-700">
                Verification Confirmation Note (Optional)
              </label>
              <textarea
                rows={2}
                value={verifyNote}
                onChange={(e) => setVerifyNote(e.target.value)}
                placeholder="Optional reviewer sign-off comment..."
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
              />
            </div>

            {actionError && (
              <p className="mt-2 text-xs font-medium text-rose-600" role="alert">
                {actionError}
              </p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => setVerifyDialogOpen(false)}
                className="h-9 rounded-lg border border-slate-200 px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => void handleVerifySubmit()}
                className="h-9 rounded-lg bg-emerald-600 px-4 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                {mutationInFlight ? 'Verifying...' : 'Confirm Verification'}
              </button>
            </div>
          </div>
        </div>
      )}

      {resolvingFlag && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="resolve-flag-title"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl text-xs">
            <h3
              id="resolve-flag-title"
              className="text-sm font-semibold text-slate-900"
            >
              Resolve Review Flag
            </h3>
            <p className="mt-1 text-slate-600">{resolvingFlag.reasonText}</p>

            <div className="mt-3 space-y-3">
              <div>
                <label className="block font-medium text-slate-700">
                  Resolution Outcome
                </label>
                <select
                  value={resolveStatus}
                  onChange={(e) =>
                    setResolveStatus(
                      e.target.value as 'RESOLVED' | 'DISMISSED'
                    )
                  }
                  className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-2.5"
                >
                  <option value="RESOLVED">Resolved</option>
                  <option value="DISMISSED">Dismissed</option>
                </select>
              </div>
              <div>
                <label className="block font-medium text-slate-700">
                  Resolution Note *
                </label>
                <textarea
                  rows={2}
                  value={resolveNote}
                  onChange={(e) => setResolveNote(e.target.value)}
                  placeholder="Explain how this flag was resolved..."
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2"
                />
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-slate-700">
                <input
                  type="checkbox"
                  checked={resolveReopenToPending}
                  onChange={(e) =>
                    setResolveReopenToPending(e.target.checked)
                  }
                  className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                />
                <span>
                  Return invoice to Pending Review when no open flags remain
                </span>
              </label>
            </div>

            {actionError && (
              <p className="mt-2 font-medium text-rose-600" role="alert">
                {actionError}
              </p>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => setResolvingFlag(null)}
                className="h-9 rounded-lg border border-slate-200 px-4 font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => void handleResolveFlagSubmit()}
                className="h-9 rounded-lg bg-indigo-600 px-4 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {mutationInFlight ? 'Saving...' : 'Submit Resolution'}
              </button>
            </div>
          </div>
        </div>
      )}

      {reopenDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reopen-dialog-title"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl text-xs">
            <h3
              id="reopen-dialog-title"
              className="text-sm font-semibold text-slate-900"
            >
              Reopen Invoice to Pending Review
            </h3>
            <p className="mt-1 text-slate-600">
              Provide an audit reason to return{' '}
              <span className="font-mono font-semibold">
                {draft.invoiceNumber}
              </span>{' '}
              back to Pending Review.
            </p>
            <textarea
              rows={3}
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              placeholder="Audit reason for reopening..."
              className="mt-3 w-full rounded-lg border border-slate-200 px-3 py-2"
            />
            {actionError && (
              <p className="mt-2 font-medium text-rose-600" role="alert">
                {actionError}
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => setReopenDialogOpen(false)}
                className="h-9 rounded-lg border border-slate-200 px-4 font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={mutationInFlight}
                onClick={() => void handleReopenSubmit()}
                className="h-9 rounded-lg bg-amber-600 px-4 font-semibold text-white hover:bg-amber-700 disabled:opacity-60"
              >
                {mutationInFlight ? 'Reopening...' : 'Confirm Reopen'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={pendingNavigation !== null}
        tone="warning"
        title="Unsaved Invoice Changes"
        description={
          <p>
            You have unsaved edits on{' '}
            <span className="font-mono font-semibold text-slate-900">
              {draft.invoiceNumber}
            </span>
            . Choose whether to save your edits, discard them, or continue
            editing.
          </p>
        }
        cancelLabel="Continue Editing"
        secondaryActionLabel="Discard Changes"
        confirmLabel="Save & Continue"
        onCancel={cancelPendingNavigation}
        onSecondaryAction={() => {
          setDraft(currentInvoice);
          commitPendingNavigation();
        }}
        onConfirm={() => {
          if (currentInvoice) {
            void saveInvoiceChanges(currentInvoice, draft).then(() => {
              commitPendingNavigation();
            });
          }
        }}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        tone="danger"
        title="Soft-Delete Invoice?"
        description={
          <p>
            Soft-delete{' '}
            <span className="font-mono font-semibold text-slate-900">
              {draft.invoiceNumber}
            </span>{' '}
            from the active workspace ledger? Audit logs remain preserved.
          </p>
        }
        cancelLabel="Keep Invoice"
        confirmLabel="Soft-Delete Invoice"
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => setDeleteDialogOpen(false)}
      />
    </div>
  );
}
