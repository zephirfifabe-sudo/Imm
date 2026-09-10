/* eslint-disable no-console */
export const logger = {
  info: (message: string, meta?: Record<string, unknown>) =>
    console.log(`[info] ${message}`, meta ?? ""),
  warn: (message: string, meta?: Record<string, unknown>) =>
    console.warn(`[warn] ${message}`, meta ?? ""),
  error: (message: string, meta?: Record<string, unknown>) =>
    console.error(`[error] ${message}`, meta ?? ""),
};
