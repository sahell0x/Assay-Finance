import { API_URL } from "@/lib/api";

/** Tell the backend a page crashed, so the person running the site finds out. Fire and
 *  forget: reporting must never cause a second error on a page that already failed. */
export function reportError(error: Error & { digest?: string }): void {
  try {
    void fetch(`${API_URL}/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      keepalive: true,
      body: JSON.stringify({
        message: `${error.name}: ${error.message}`.slice(0, 2000),
        digest: error.digest ?? null,
        path: typeof window !== "undefined" ? window.location.pathname : null,
      }),
    }).catch(() => {});
  } catch {
    // nothing to do
  }
}
