"use client";

import { useEffect } from "react";

import { reportError } from "@/lib/report-error";

/** The last line of defence, used when the root layout itself fails. It replaces the
 *  whole document, so it carries its own <html> and plain inline styles. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportError(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, sans-serif",
          background: "#f4f6f5",
          color: "#13201a",
          display: "grid",
          placeItems: "center",
          minHeight: "100vh",
        }}
      >
        <div style={{ maxWidth: 440, padding: 24 }}>
          <h1 style={{ fontSize: 28, margin: "0 0 12px" }}>Something went wrong</h1>
          <p style={{ lineHeight: 1.6, color: "#56645e", margin: "0 0 20px" }}>
            The site could not load. Your analyses and credits are safe. Please try again
            in a moment.
          </p>
          <button
            onClick={() => reset()}
            style={{
              background: "#13201a",
              color: "#fff",
              border: 0,
              borderRadius: 8,
              padding: "10px 16px",
              fontSize: 15,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
