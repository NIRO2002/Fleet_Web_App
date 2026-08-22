const PREFIX = 'fleet:'

/** Reads a JSON value persisted for this browser tab's session; falls back silently if absent or unreadable. */
export function readSession<T>(key: string, fallback: T): T {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key)
    if (raw === null) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

/** Persists a JSON-serializable value for the current tab session (cleared when the tab/browser closes). */
export function writeSession<T>(key: string, value: T): void {
  try {
    window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    // Storage unavailable (private mode, quota) — state just won't persist across navigation.
  }
}

/** Removes persisted keys, e.g. when a page's "Refresh" control should discard cached state. */
export function clearSession(keys: string[]): void {
  try {
    keys.forEach((key) => window.sessionStorage.removeItem(PREFIX + key))
  } catch {
    // ignore
  }
}
