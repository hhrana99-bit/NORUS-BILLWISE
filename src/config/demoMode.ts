export interface DemoModeEnv {
  VITE_DEMO_MODE?: string | boolean;
  MODE?: string;
  PROD?: boolean;
  DEV?: boolean;
}

export const DEMO_MODE_DISABLED_ACTION_MESSAGE =
  'Demo actions are unavailable in read-only sample mode.';

export function resolveDemoMode(env?: DemoModeEnv): boolean {
  if (!env) return false;
  const raw = env.VITE_DEMO_MODE;
  if (typeof raw === 'boolean') return raw;
  if (typeof raw !== 'string') return false;
  return raw.trim().toLowerCase() === 'true';
}

export function isDemoModeEnabled(): boolean {
  const metaEnv = (
    import.meta as unknown as {
      env?: DemoModeEnv;
    }
  ).env;
  return resolveDemoMode(metaEnv);
}
