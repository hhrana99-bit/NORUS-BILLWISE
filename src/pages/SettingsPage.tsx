import { Check, Lock, RefreshCw, ShieldCheck } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Card, CardHeader } from '../components/common/Card';
import { INITIAL_SETTINGS } from '../data/mockData';
import { useWorkspace } from '../state/WorkspaceContext';
import type { WorkspaceSettings } from '../types/domain';

export function SettingsPage() {
  const { settings, updateSettings, resetDemoWorkspace } = useWorkspace();
  const [form, setForm] = useState<WorkspaceSettings>(settings);
  const [savedNotice, setSavedNotice] = useState(false);
  const [resetNotice, setResetNotice] = useState(false);

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    updateSettings(form);
    setResetNotice(false);
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 2500);
  };

  const handleReset = () => {
    resetDemoWorkspace();
    setForm(INITIAL_SETTINGS);
    setSavedNotice(false);
    setResetNotice(true);
    setTimeout(() => setResetNotice(false), 2500);
  };

  return (
    <form onSubmit={handleSave} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Workspace Settings</h2>
          <p className="text-xs text-slate-500">
            Frontend-only prototype preferences saved locally in your browser.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-700 hover:bg-slate-50 whitespace-nowrap"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {resetNotice ? 'Demo Data Restored' : 'Reset Demo Data'}
          </button>
          <button
            type="submit"
            className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-indigo-600 px-4 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap"
          >
            {savedNotice ? (
              <>
                <Check className="h-3.5 w-3.5" />
                Saved Locally
              </>
            ) : (
              'Save Settings'
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Workspace Profile"
            subtitle="Active firm / client workspace identity"
          />
          <div className="space-y-4 p-5 text-xs">
            <div>
              <label className="block font-medium text-slate-700">
                Workspace Name
              </label>
              <input
                type="text"
                value={form.workspaceName}
                onChange={(e) =>
                  setForm((p) => ({ ...p, workspaceName: e.target.value }))
                }
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block font-medium text-slate-700">Firm Type</label>
                <input
                  type="text"
                  value={form.firmType}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, firmType: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700">
                  Workspace Code
                </label>
                <input
                  type="text"
                  value={form.workspaceCode}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, workspaceCode: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-slate-900 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Company Information"
            subtitle="Sample Indian GST entity details"
          />
          <div className="space-y-4 p-5 text-xs">
            <div>
              <label className="block font-medium text-slate-700">
                Legal Entity Name
              </label>
              <input
                type="text"
                value={form.legalEntityName}
                onChange={(e) =>
                  setForm((p) => ({ ...p, legalEntityName: e.target.value }))
                }
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block font-medium text-slate-700">
                  Company GSTIN (Sample)
                </label>
                <input
                  type="text"
                  value={form.companyGstin}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, companyGstin: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-slate-900 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700">
                  Company PAN (Sample)
                </label>
                <input
                  type="text"
                  value={form.companyPan}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, companyPan: e.target.value }))
                  }
                  className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 font-mono text-slate-900 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block font-medium text-slate-700">
                Registered Address
              </label>
              <input
                type="text"
                value={form.registeredAddress}
                onChange={(e) =>
                  setForm((p) => ({ ...p, registeredAddress: e.target.value }))
                }
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 px-3 text-slate-900 focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Invoice Verification Preferences"
            subtitle="Controls governing review workflow and exception checks"
          />
          <div className="divide-y divide-slate-100 px-5 py-2 text-xs">
            <div className="flex items-start justify-between gap-4 py-3.5">
              <div>
                <div className="flex items-center gap-1.5 font-semibold text-slate-900">
                  <Lock className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Mandatory Human Review Gate</span>
                </div>
                <p className="mt-1 text-slate-500">
                  Product Principle: AI suggestions never automatically become approved
                  accounting records.
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
                checked={form.enableDuplicateWarnings}
                onChange={(e) =>
                  setForm((p) => ({ ...p, enableDuplicateWarnings: e.target.checked }))
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
                  Surface reconciliation variance banners when Taxable + GST differs
                  from Total.
                </p>
              </div>
              <input
                type="checkbox"
                checked={form.autoFlagTaxMismatch}
                onChange={(e) =>
                  setForm((p) => ({ ...p, autoFlagTaxMismatch: e.target.checked }))
                }
                className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Regional & Tax Preferences"
            subtitle="Configured for initial India market launch"
          />
          <div className="grid grid-cols-1 gap-4 p-5 text-xs sm:grid-cols-2">
            <div>
              <label className="block font-medium text-slate-700">Currency</label>
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
              <label className="block font-medium text-slate-700">Date Format</label>
              <input
                type="text"
                readOnly
                value={form.dateFormat}
                className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-slate-700"
              />
            </div>
            <div>
              <label className="block font-medium text-slate-700">Tax Regime</label>
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
            subtitle="Local prototype notification triggers"
          />
          <div className="divide-y divide-slate-100 px-5 py-2 text-xs">
            <label className="flex cursor-pointer items-center justify-between py-3.5">
              <span className="font-medium text-slate-800">
                Alert on newly flagged invoices
              </span>
              <input
                type="checkbox"
                checked={form.notifyFlaggedInvoices}
                onChange={(e) =>
                  setForm((p) => ({ ...p, notifyFlaggedInvoices: e.target.checked }))
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
                checked={form.notifyDuplicateAlerts}
                onChange={(e) =>
                  setForm((p) => ({ ...p, notifyDuplicateAlerts: e.target.checked }))
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
                checked={form.notifyDailyDigest}
                onChange={(e) =>
                  setForm((p) => ({ ...p, notifyDailyDigest: e.target.checked }))
                }
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
              />
            </label>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Data Protection & Privacy"
            subtitle="NORUS BILLWISE security posture for prototype and production"
          />
          <div className="space-y-3 p-5 text-xs leading-relaxed text-slate-600">
            <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              <p>
                <strong>Prototype Isolation:</strong> All data in Task 001 resides
                strictly in browser memory and optional <code>localStorage</code>. No
                documents or financial fields leave your browser.
              </p>
            </div>
            <p>
              Do not upload real confidential client invoices into this prototype.
              Production data encryption, tenant isolation, role-based access control,
              and audit logging will be implemented with the Python FastAPI + PostgreSQL
              backend.
            </p>
          </div>
        </Card>
      </div>
    </form>
  );
}
