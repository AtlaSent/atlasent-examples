import { defineConfig } from 'vite';

/**
 * Minimal Vite config for the AtlaSent browser guard example.
 *
 * Key point: Vite exposes env vars prefixed with VITE_ to the browser bundle
 * via import.meta.env. It does NOT expose process.env — accessing
 * process.env in a browser bundle crashes at runtime.
 *
 * The SDK (and this example) uses import.meta.env.VITE_ATLASENT_API_KEY
 * so it works safely in browsers, edge workers (Cloudflare Workers,
 * Deno Deploy, etc.), and Vite dev mode.
 */
export default defineConfig({
  // No framework plugins needed for this vanilla TS example.
  build: {
    target: 'es2022',
  },
});
