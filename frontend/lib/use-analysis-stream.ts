"use client";

import * as React from "react";

import { API_URL } from "@/lib/api";
import type { NodeEvent, PipelineStep } from "@/lib/types";

export interface StreamState {
  nodes: Record<string, NodeEvent>;
  pipeline: PipelineStep[];
  status: "connecting" | "queued" | "running" | "complete" | "failed" | "timeout";
  currentNode: string | null;
  replaying: boolean;
  error: string | null;
}

type Frame =
  | { type: "snapshot"; status: string; current_node: string | null; cached: boolean; nodes: NodeEvent[]; pipeline: PipelineStep[] }
  | { type: "node"; node: string; status: NodeEvent["status"]; duration_ms?: number | null; detail?: Record<string, unknown>; replayed?: boolean }
  | { type: "replay"; speedup: number; events: number }
  | { type: "done"; status: string; error?: string | null; replayed?: boolean }
  | { type: "error"; message: string };

/** Subscribes to an analysis's server-sent events.
 *
 *  The stream replays a full snapshot on connect, so a browser that refreshes halfway
 *  through a run rebuilds the checklist immediately rather than showing ten empty rows
 *  for a job that is nearly finished. A completed run replays its recorded timeline, so
 *  a cached result still shows its pipeline.
 */
export function useAnalysisStream(analysisId: string | null, enabled = true): StreamState {
  const [state, setState] = React.useState<StreamState>({
    nodes: {},
    pipeline: [],
    status: "connecting",
    currentNode: null,
    replaying: false,
    error: null,
  });

  React.useEffect(() => {
    if (!analysisId || !enabled) return;

    const source = new EventSource(`${API_URL}/analyses/${analysisId}/stream`, {
      withCredentials: true,
    });

    source.onmessage = (event) => {
      let frame: Frame;
      try {
        frame = JSON.parse(event.data) as Frame;
      } catch {
        return;
      }

      setState((prev) => {
        switch (frame.type) {
          case "snapshot": {
            const nodes: Record<string, NodeEvent> = {};
            for (const n of frame.nodes) nodes[n.node] = n;
            return {
              ...prev,
              nodes,
              pipeline: frame.pipeline,
              status: (frame.status as StreamState["status"]) ?? "running",
              currentNode: frame.current_node,
            };
          }
          case "replay":
            return { ...prev, replaying: true };
          case "node":
            return {
              ...prev,
              status: prev.status === "queued" ? "running" : prev.status,
              currentNode: frame.status === "start" ? frame.node : prev.currentNode,
              nodes: {
                ...prev.nodes,
                [frame.node]: {
                  node: frame.node,
                  status: frame.status,
                  duration_ms: frame.duration_ms ?? null,
                  detail: frame.detail ?? null,
                },
              },
            };
          case "done":
            return {
              ...prev,
              status: (frame.status as StreamState["status"]) ?? "complete",
              currentNode: null,
              replaying: false,
              error: frame.error ?? null,
            };
          case "error":
            return { ...prev, status: "failed", error: frame.message };
          default:
            return prev;
        }
      });

      if (frame.type === "done") source.close();
    };

    source.onerror = () => {
      // EventSource retries on its own; only give up once the browser has.
      if (source.readyState === EventSource.CLOSED) {
        setState((prev) =>
          prev.status === "complete" || prev.status === "failed"
            ? prev
            : { ...prev, status: "failed", error: "The connection to the analysis dropped." },
        );
      }
    };

    return () => source.close();
  }, [analysisId, enabled]);

  return state;
}
