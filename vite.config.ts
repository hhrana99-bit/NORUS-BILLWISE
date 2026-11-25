import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';
import {fileURLToPath} from 'url';
import {defineConfig, loadEnv} from 'vite';
import {resolveDemoMode} from './src/config/demoMode.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const DEMO_MODE_PRODUCTION_WARNING =
  '[NORUS BILLWISE SECURITY WARNING] VITE_DEMO_MODE="true" is active in a production build. Sign-in is bypassed with read-only synthetic sample data. Do NOT deploy this build for real customer workspaces.';

export function checkProductionDemoModeWarning(
  mode: string,
  envDir: string = process.cwd(),
  warn: (message: string) => void = console.warn,
  processEnv: NodeJS.ProcessEnv = process.env
): boolean {
  const fileEnv = loadEnv(mode, envDir, 'VITE_');
  const effectiveDemoMode =
    processEnv.VITE_DEMO_MODE ?? fileEnv.VITE_DEMO_MODE;
  if (mode === 'production' && resolveDemoMode({VITE_DEMO_MODE: effectiveDemoMode})) {
    warn(DEMO_MODE_PRODUCTION_WARNING);
    return true;
  }
  return false;
}

export default defineConfig(({mode}) => {
  checkProductionDemoModeWarning(mode, process.cwd());

  return {
    plugins: [
      react(),
      tailwindcss(),
      // Copies src/assets into dist/ so root-relative URLs like
      // "/src/assets/images/..." (e.g. generate_image output) still resolve
      // in production builds. Do not remove.
      {
        name: 'copy-unbundled-src-assets',
        apply: 'build',
        closeBundle(error?: Error): void {
          if (error) {
            return;
          }
          const distDir = path.resolve(__dirname, 'dist');
          const srcAssets = path.resolve(__dirname, 'src/assets');
          const distAssets = path.resolve(distDir, 'src/assets');
          if (fs.existsSync(distDir) && fs.existsSync(srcAssets)) {
            fs.cpSync(srcAssets, distAssets, {recursive: true, force: true});
          }
        },
      },
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
