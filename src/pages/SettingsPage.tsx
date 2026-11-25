import { Check, Lock, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Card, CardHeader } from '../components/common/Card';
import { formatApiErrorMessage } from '../services/apiClient';
import { useWorkspace } from '../state/WorkspaceContext';
import type { WorkspaceSettings } from '../types/domain';

export function SettingsPage() {
  const {
    activeWorkspaceId,
    activeWorkspaceRole,
    settings,
    localUiPrefs,
    updateLocalUiPrefs,
    updateSettingsAction,
    mutationInFlight,
  } = useWorkspace();

  const [form, setForm] = useState<WorkspaceSettings>(settings);
  const [roundingInput, setRoundingInput] = useState<string>(
    String(settings.roundingTolerance ?? 1)
  );
  const [savedNotice, setSavedNotice] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const isWorkspaceAdmin = activeWorkspaceRole === 'WORKSPACE_ADMIN';

  useEffect(() => {
    setForm(settings);
    setRoundingInput(String(settings.roundingTolerance ?? 1));
    setSaveError(null);
    setSavedNotice(false);
  }, [settings, activeWorkspaceId]);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!isWorkspaceAdmin) return;
    setSaveError(null);

    const parsedTolerance = Number(roundingInput);
    if (
      !Number.isFinite(parsedTolerance) ||
      parsedTolerance < 0 ||
      parsedTolerance > 100
    ) {
      setSaveError('Rounding tolerance must be between 0.00 and 100.00.');
      return;
    }

    try {
      await updateSettingsAction({
        legalEntityName: form.legalEntityName.trim(),
        companyGstin: form.companyGstin.trim() || null,
        companyPan: form.companyPan.trim() || null,
        registeredAddress: form.registeredAddress.trim(),
        enableDuplicateWarnings: form.enableDuplicateWarnings,
        autoFlagTaxMismatch: form.autoFlagTaxMismatch,
        roundingTolerance: parsedTolerance.toFixed(2),
        notifyFlaggedInvoices: form.notifyFlaggedInvoices,
        notifyDailyDigest: form.notifyDailyDigest,
        notifyDuplicateAlerts: form.notifyDuplicateAlerts,
      });
      setSavedNotice(true);
      setTimeout(() => setSavedNotice(false), 2500);
    } catch (err) {
      setSaveError(formatApiErrorMessage(err));
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Workspace Settings
          </h2>
          <p className="text-xs text-slate-500">
            Server-persisted accounting, GST entity, and notification settings
            for this workspace.
          </p>
        </div>

        <button
          type="submit"
          disabled={!isWorkspaceAdmin || mutationInFlight}
          className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-indigo-600 px-4 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
        >
          {savedNotice ? (
            <>
              <Check className="h-3.5 w-3.5" />
              Settings Saved
            </>
          ) : mutationInFlight ? (
            'Saving...'
          ) : (
            'Save Workspace Settings'
          )}
        </button>
      </div>

      {!isWorkspaceAdmin && (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
          <Lock className="h-4 w-4 shrink-0 text-slate-500" />
          <span>
            Read-only workspace settings: only a <strong>Workspace Admin</strong>{' '}
            can modify persisted workspace preferences.
          </span>
        </div>
      )}

      {saveError && (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-900"
        >
          {saveError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Workspace Profile"
            subtitle="Active tenant workspace identity (read-only)"
          />
          <div className="space-y-4 p-5 text-xs">
            <div>
              <label className="block font-medium text-slate-700">
                Workspace Name
              </label>
              <input
                type="text"
                readOnly
                value={form.workspaceName}
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block font-medium text-slate-700">
                  Firm Type
                </label>
                <input
                  type="text"
                  readOnly
                  value={form.firmType}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700">
                  Workspace Code
                </label>
                <input
                  type="text"
                  readOnly
                  value={form.workspaceCode}
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 font-mono text-slate-700"
                />
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Company Information"
            subtitle="Indian GST legal entity details persisted to workspace_settings"
          />
          <div className="space-y-4 p-5 text-xs">
            <div>
              <label className="block font-medium text-slate-700">
                Legal Entity Name
              </label>
              <input
                type="text"
                disabled={!isWorkspaceAdmin}
                value={form.legalEntityName}
                onChange={(e) =>
                  setForm((p) => ({ ...p, legalEntityName: e.target.value }))
                }
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block font-medium text-slate-700">
                  Company GSTIN
                </label>
                <input
                  type="text"
                  disabled={!isWorkspaceAdmin}
                  value={form.companyGstin}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, companyGstin: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-slate-900 focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700">
                  Company PAN
                </label>
                <input
                  type="text"
                  disabled={!isWorkspaceAdmin}
                  value={form.companyPan}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, companyPan: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-slate-900 focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
                />
              </div>
            </div>
            <div>
              <label className="block font-medium text-slate-700">
                Registered Address
              </label>
              <input
                type="text"
                disabled={!isWorkspaceAdmin}
                value={form.registeredAddress}
                onChange={(e) =>
                  setForm((p) => ({ ...p, registeredAddress: e.target.value }))
                }
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
              />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Invoice Verification Preferences"
            subtitle="Controls governing review workflow and reconciliation checks"
          />
          <div className="divide-y divide-slate-100 px-5 py-2 text-xs">
            <div className="flex items-start justify-between gap-4 py-3.5">
              <div>
                <div className="flex items-center gap-1.5 font-semibold text-slate-900">
                  <Lock className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Mandatory Human Review Gate</span>
                </div>
                <p className="mt-1 text-slate-500">
                  Product Principle: Invoices never automatically become
                  verified accounting records without explicit human sign-off.
                </p>
              </div>
              <span className="shrink-0 text-xs font-semibold text-emerald-700">
                Enforced
              </span>
            </div>

            <label className="flex cursor-pointer items-start justify-between gap-4 py-3.5">
              <div>
                <p className="font-semibold text-slate-900">
                  Duplicate Invoice Warnings
                </p>
                <p className="mt-1 text-slate-500">
                  Produce advisory warnings on potential duplicate bills without
                  auto-rejecting.
                </p>
              </div>
              <input
                type="checkbox"
                disabled={!isWorkspaceAdmin}
                checked={form.enableDuplicateWarnings}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    enableDuplicateWarnings: e.target.checked,
                  }))
                }
                className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>

            <label className="flex cursor-pointer items-start justify-between gap-4 py-3.5">
              <div>
                <p className="font-semibold text-slate-900">
                  Highlight Tax / Total Arithmetic Mismatch
                </p>
                <p className="mt-1 text-slate-500">
                  Surface reconciliation variance banners when Taxable + GST
                  differs from Total beyond tolerance.
                </p>
              </div>
              <input
                type="checkbox"
                disabled={!isWorkspaceAdmin}
                checked={form.autoFlagTaxMismatch}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    autoFlagTaxMismatch: e.target.checked,
                  }))
                }
                className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>

            <div className="flex items-center justify-between gap-4 py-3.5">
              <div>
                <p className="font-semibold text-slate-900">
                  Rounding Tolerance (INR)
                </p>
                <p className="mt-1 text-slate-500">
                  Permitted paisa/rupee rounding difference before flagging
                  VARIANCE_DETECTED.
                </p>
              </div>
              <input
                type="number"
                step="0.01"
                min="0"
                max="100"
                disabled={!isWorkspaceAdmin}
                value={roundingInput}
                onChange={(e) => setRoundingInput(e.target.value)}
                className="h-9 w-24 rounded-lg border border-slate-200 px-2.5 text-right font-mono text-xs disabled:bg-slate-50"
              />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Regional & Tax Preferences"
            subtitle="Configured for initial India market launch"
          />
          <div className="grid grid-cols-1 gap-4 p-5 text-xs sm:grid-cols-2">
            <div>
              <label className="block font-medium text-slate-700">
                Currency
              </label>
              <input
                type="text"
                readOnly
                value="INR (₹) — Indian Rupee"
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700">
                Financial Year
              </label>
              <input
                type="text"
                readOnly
                value={form.financialYear}
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700">
                Date Format
              </label>
              <input
                type="text"
                readOnly
                value={form.dateFormat}
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700">
                Tax Regime
              </label>
              <input
                type="text"
                readOnly
                value={form.taxRegime}
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Notification Preferences"
            subtitle="Workspace alert toggles stored on server"
          />
          <div className="divide-y divide-slate-100 px-5 py-2 text-xs">
            <label className="flex cursor-pointer items-center justify-between py-3.5">
              <span className="font-medium text-slate-800">
                Alert on newly flagged invoices
              </span>
              <input
                type="checkbox"
                disabled={!isWorkspaceAdmin}
                checked={form.notifyFlaggedInvoices}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    notifyFlaggedInvoices: e.target.checked,
                  }))
                }
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </label>
            <label className="flex cursor-pointer items-center justify-between py-3.5">
              <span className="font-medium text-slate-800">
                Alert on duplicate invoice warnings
              </span>
              <input
                type="checkbox"
                disabled={!isWorkspaceAdmin}
                checked={form.notifyDuplicateAlerts}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    notifyDuplicateAlerts: e.target.checked,
                  }))
                }
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </label>
            <label className="flex cursor-pointer items-center justify-between py-3.5">
              <span className="font-medium text-slate-800">
                Daily review queue digest
              </span>
              <input
                type="checkbox"
                disabled={!isWorkspaceAdmin}
                checked={form.notifyDailyDigest}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    notifyDailyDigest: e.target.checked,
                  }))
                }
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </label>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Browser-Only UI Preferences"
            subtitle="Stored strictly in local browser storage (not synced to server)"
          />
          <div className="space-y-4 p-5 text-xs">
            <label className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-3">
              <div>
                <p className="font-medium text-slate-900">
                  Compact Ledger Table Rows
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  Reduces vertical padding in Invoices and Suppliers tables for
                  this browser only.
                </p>
              </div>
              <input
                type="checkbox"
                checked={localUiPrefs.compactTables}
                onChange={(e) =>
                  updateLocalUiPrefs({
                    ...localUiPrefs,
                    compactTables: e.target.checked,
                  })
                }
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </label>

            <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-slate-600">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              <p className="leading-relaxed">
                Authentication uses HttpOnly cookies with CSRF header protection;
                no session secrets are stored in browser localStorage.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </form>
  );
}
