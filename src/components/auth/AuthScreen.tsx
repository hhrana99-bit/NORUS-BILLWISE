import { AlertCircle, ArrowRight, Lock, Mail, ShieldCheck, User, Building2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { formatApiErrorMessage } from '../../services/apiClient';
import { useWorkspace } from '../../state/WorkspaceContext';
import { Logo } from '../common/Logo';

const FIRM_TYPES = [
  'Chartered Accountancy Practice',
  'Corporate Finance Team',
  'Bookkeeping & Advisory',
  'Tax Consultancy',
];

export function AuthScreen() {
  const { login, register, sessionExpiredMessage, clearSessionExpiredMessage } =
    useWorkspace();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [organizationName, setOrganizationName] = useState('');
  const [firmType, setFirmType] = useState(FIRM_TYPES[0]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const switchMode = (nextMode: 'login' | 'register') => {
    setMode(nextMode);
    setError(null);
    clearSessionExpiredMessage();
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    clearSessionExpiredMessage();

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !trimmedEmail.includes('@')) {
      setError('Enter a valid work email address.');
      return;
    }

    if (mode === 'register') {
      if (!fullName.trim()) {
        setError('Full name is required to create an account.');
        return;
      }
      const nonWhitespacePasswordChars = password.replace(/\s+/g, '').length;
      if (password.length < 12 || nonWhitespacePasswordChars < 12) {
        setError(
          'Password must be at least 12 non-whitespace characters.'
        );
        return;
      }
    } else if (!password) {
      setError('Enter your password to sign in.');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'login') {
        await login(trimmedEmail, password);
      } else {
        await register({
          email: trimmedEmail,
          password,
          fullName: fullName.trim(),
          organizationName: organizationName.trim() || undefined,
          firmType,
        });
      }
    } catch (err) {
      setError(formatApiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 lg:flex-row">
      <div className="flex flex-col justify-between bg-slate-950 px-6 py-8 text-slate-200 sm:px-10 lg:w-[440px] lg:shrink-0 lg:border-r lg:border-slate-800/80 lg:py-12">
        <div>
          <Logo />
          <div className="mt-10 space-y-4">
            <p className="inline-flex items-center gap-2 rounded-md border border-indigo-500/30 bg-indigo-950/60 px-2.5 py-1 text-xs font-medium text-indigo-200">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              Human-in-the-Loop Accounting Controls
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-white">
              Supplier Invoice Verification &amp; GST Audit Workspace
            </h1>
            <p className="text-sm leading-relaxed text-slate-400">
              Transform supplier bills into structured, reviewable accounting
              records with explicit arithmetic reconciliation, duplicate checks,
              and immutable reviewer sign-off.
            </p>
          </div>
        </div>

        <div className="mt-8 space-y-3 border-t border-slate-800/80 pt-6 text-xs text-slate-400">
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3.5">
            <p className="font-medium text-slate-200">
              Mandatory Human Verification Gate
            </p>
            <p className="mt-1 leading-relaxed text-slate-400">
              No invoice is automatically approved or posted. Every record
              requires explicit reviewer action backed by source evidence.
            </p>
          </div>
          <div className="flex items-center justify-between text-[11px] text-slate-500">
            <span>NORUS AI · NORUS BILLWISE</span>
            <span>India GST Edition</span>
          </div>
        </div>
      </div>

      <main className="flex flex-1 items-center justify-center bg-slate-50 px-4 py-10 sm:px-8">
        <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-1">
            <button
              type="button"
              onClick={() => switchMode('login')}
              className={`flex-1 rounded-md py-2 text-xs font-semibold transition-colors ${
                mode === 'login'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => switchMode('register')}
              className={`flex-1 rounded-md py-2 text-xs font-semibold transition-colors ${
                mode === 'register'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Create Account
            </button>
          </div>

          <div className="mt-6">
            <h2 className="text-lg font-semibold text-slate-900">
              {mode === 'login'
                ? 'Sign in to your practice workspace'
                : 'Create your NORUS BILLWISE workspace'}
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {mode === 'login'
                ? 'Authenticate with HttpOnly cookie session & CSRF protection.'
                : 'Register a new user and initialize a firm workspace.'}
            </p>
          </div>

          {(sessionExpiredMessage || error) && (
            <div
              role="alert"
              className="mt-4 flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-800"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
              <span>{error ?? sessionExpiredMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            {mode === 'register' && (
              <>
                <div>
                  <label
                    htmlFor="auth-full-name"
                    className="block text-xs font-medium text-slate-700"
                  >
                    Full Name
                  </label>
                  <div className="relative mt-1">
                    <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      id="auth-full-name"
                      type="text"
                      required
                      autoComplete="name"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="CA Ananya Deshmukh"
                      className="h-10 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label
                      htmlFor="auth-org-name"
                      className="block text-xs font-medium text-slate-700"
                    >
                      Firm / Organization Name
                    </label>
                    <div className="relative mt-1">
                      <Building2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        id="auth-org-name"
                        type="text"
                        value={organizationName}
                        onChange={(e) => setOrganizationName(e.target.value)}
                        placeholder="Deshmukh & Associates"
                        className="h-10 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                      />
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="auth-firm-type"
                      className="block text-xs font-medium text-slate-700"
                    >
                      Practice Type
                    </label>
                    <select
                      id="auth-firm-type"
                      value={firmType}
                      onChange={(e) => setFirmType(e.target.value)}
                      className="mt-1 h-10 w-full rounded-lg border border-slate-300 bg-white px-2.5 text-xs text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                    >
                      {FIRM_TYPES.map((ft) => (
                        <option key={ft} value={ft}>
                          {ft}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </>
            )}

            <div>
              <label
                htmlFor="auth-email"
                className="block text-xs font-medium text-slate-700"
              >
                Work Email
              </label>
              <div className="relative mt-1">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="partner@firm.in"
                  className="h-10 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="auth-password"
                className="block text-xs font-medium text-slate-700"
              >
                Password
              </label>
              <div className="relative mt-1">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  id="auth-password"
                  type="password"
                  required
                  autoComplete={
                    mode === 'login' ? 'current-password' : 'new-password'
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={
                    mode === 'register'
                      ? 'Minimum 12 characters'
                      : 'Enter your password'
                  }
                  className="h-10 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
                />
              </div>
              {mode === 'register' && (
                <p className="mt-1 text-[11px] text-slate-500">
                  Minimum 12 non-whitespace characters required.
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span>
                {submitting
                  ? mode === 'login'
                    ? 'Signing in...'
                    : 'Creating account...'
                  : mode === 'login'
                    ? 'Sign In'
                    : 'Create Account'}
              </span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
