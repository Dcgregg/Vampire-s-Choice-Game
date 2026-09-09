/**
 * Sync layer config. The client talks to the backend at the same origin by
 * default (the ingress routes "/api" to the backend), so no URL needs to be
 * hard-coded. An optional VITE_BACKEND_URL can override the base for local dev.
 */
const raw = ((import.meta.env.VITE_BACKEND_URL as string | undefined) ?? '').replace(/\/$/, '');
export const API_BASE = `${raw}/api`;
