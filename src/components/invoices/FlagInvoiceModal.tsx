import { Flag, X } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  CUSTOM_FLAG_OPTION,
  PREDEFINED_FLAG_REASONS,
  resolveFlagReason,
} from '../../services/invoiceService';

export function FlagInvoiceModal({
  open,
  invoiceNumber,
  initialReason,
  hasArithmeticMismatch,
  hasDuplicateWarning,
  onConfirm,
  onClose,
}: {
  open: boolean;
  invoiceNumber: string;
  initialReason?: string;
  hasArithmeticMismatch: boolean;
  hasDuplicateWarning: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}) {
  const [selectedReason, setSelectedReason] = useState<string>(
    PREDEFINED_FLAG_REASONS[0]
  );
  const [customReason, setCustomReason] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const firstRadioRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;

    const trimmedInitial = initialReason?.trim() ?? '';
    const matchesPredefined = PREDEFINED_FLAG_REASONS.find(
      (r) => r === trimmedInitial
    );

    if (matchesPredefined) {
      setSelectedReason(matchesPredefined);
      setCustomReason('');
    } else if (trimmedInitial) {
      setSelectedReason(CUSTOM_FLAG_OPTION);
      setCustomReason(trimmedInitial);
    } else if (hasArithmeticMismatch) {
      setSelectedReason(PREDEFINED_FLAG_REASONS[0]);
      setCustomReason('');
    } else if (hasDuplicateWarning) {
      setSelectedReason(PREDEFINED_FLAG_REASONS[1]);
      setCustomReason('');
    } else {
      setSelectedReason(PREDEFINED_FLAG_REASONS[0]);
      setCustomReason('');
    }
    setErrorMsg('');

    setTimeout(() => firstRadioRef.current?.focus(), 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, initialReason, hasArithmeticMismatch, hasDuplicateWarning, onClose]);

  if (!open) return null;

  const isCustomMode = selectedReason === CUSTOM_FLAG_OPTION;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const resolved = resolveFlagReason({ selectedReason, customReason });
    if (!resolved.ok) {
      setErrorMsg(resolved.error);
      return;
    }
    onConfirm(resolved.reason);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="flag-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
              <Flag className="h-4 w-4" />
            </div>
            <div>
              <h2 id="flag-modal-title" className="text-sm font-semibold text-slate-900">
                Flag Invoice for Review
              </h2>
              <p className="font-mono text-xs text-slate-500">{invoiceNumber}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close flag dialog"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          <fieldset className="space-y-2">
            <legend className="text-xs font-semibold text-slate-800">
              Select Flag Reason
            </legend>
            <div className="space-y-1.5">
              {PREDEFINED_FLAG_REASONS.map((reason, idx) => (
                <label
                  key={reason}
                  className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-xs transition-colors ${
                    selectedReason === reason
                      ? 'border-rose-300 bg-rose-50/70 text-rose-950'
                      : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <input
                    ref={idx === 0 ? firstRadioRef : undefined}
                    type="radio"
                    name="flagReasonOption"
                    value={reason}
                    checked={selectedReason === reason}
                    onChange={() => {
                      setSelectedReason(reason);
                      setErrorMsg('');
                    }}
                    className="h-3.5 w-3.5 text-rose-600 focus:ring-rose-500"
                  />
                  <span>{reason}</span>
                </label>
              ))}

              <label
                className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-xs transition-colors ${
                  isCustomMode
                    ? 'border-rose-300 bg-rose-50/70 text-rose-950'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="flagReasonOption"
                  value={CUSTOM_FLAG_OPTION}
                  checked={isCustomMode}
                  onChange={() => {
                    setSelectedReason(CUSTOM_FLAG_OPTION);
                    setErrorMsg('');
                  }}
                  className="h-3.5 w-3.5 text-rose-600 focus:ring-rose-500"
                />
                <span className="font-medium">Custom reason (specify below)</span>
              </label>
            </div>
          </fieldset>

          <div>
            <label
              htmlFor="custom-flag-reason-input"
              className="block text-xs font-medium text-slate-700"
            >
              {isCustomMode
                ? 'Custom Flag Reason (Required)'
                : 'Optional Additional Details / Custom Note'}
            </label>
            <textarea
              id="custom-flag-reason-input"
              rows={3}
              value={customReason}
              onChange={(e) => {
                setCustomReason(e.target.value);
                if (errorMsg) setErrorMsg('');
              }}
              placeholder={
                isCustomMode
                  ? 'Describe why this invoice is being held for review...'
                  : 'Optional note appended to the selected flag reason...'
              }
              className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-rose-500 focus:outline-none focus:ring-2 focus:ring-rose-500/15"
            />
            {errorMsg && (
              <p className="mt-1.5 text-xs font-medium text-rose-600" role="alert">
                {errorMsg}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-3">
            <button
              type="button"
              onClick={onClose}
              className="h-9 rounded-lg border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-rose-600 px-4 text-xs font-semibold text-white hover:bg-rose-700"
            >
              <Flag className="h-3.5 w-3.5" />
              Confirm Flag
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
