"use client";

import { useEffect, useRef, useState } from "react";

interface BulkEvent {
  event: string;
  job_id?: string;
  processed?: number;
  total?: number;
  stats?: any;
  error?: string;
}

interface UseBulkWSResult {
  connected: boolean;
  event: BulkEvent | null;
  status: "idle" | "running" | "completed" | "failed";
  progress: number;
  stats: any;
  error: string | null;
}

export function useBulkWS(jobId: string): UseBulkWSResult {
  const [connected, setConnected] = useState(false);
  const [event, setEvent] = useState<BulkEvent | null>(null);
  const [status, setStatus] = useState<
    "idle" | "running" | "completed" | "failed"
  >("idle");
  const [progress, setProgress] = useState(0);
  const [stats, setStats] = useState<any>({});
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) return;

    // Get JWT token for authorization
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;

    if (!token) {
      console.warn("No access token found for WS auth");
      return;
    }

    const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

    // Final WS URL
    const url = `${WS_URL}/ws/bulk/${jobId}?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setStatus("running");
    };

    ws.onmessage = (msg) => {
      try {
        const payload: BulkEvent = JSON.parse(msg.data);
        setEvent(payload);

        // ----------------------------
        // PROGRESS EVENT
        // ----------------------------
        if (payload.event === "progress") {
          const p = payload.processed ?? 0;
          const t = payload.total ?? 0;

          setProgress(t > 0 ? Math.round((p / t) * 100) : 0);

          if (payload.stats) setStats(payload.stats);
        }

        // ----------------------------
        // COMPLETED EVENT
        // ----------------------------
        if (payload.event === "completed") {
          setStatus("completed");
          setProgress(100);
          if (payload.stats) setStats(payload.stats);
        }

        // ----------------------------
        // FAILED EVENT
        // ----------------------------
        if (payload.event === "failed") {
          setStatus("failed");
          setError(payload.error || "Bulk job failed");
        }
      } catch (err) {
        console.error("WS parse error:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("Bulk WS error:", err);
      setConnected(false);
    };

    ws.onclose = () => {
      console.log("Bulk WS closed");
      setConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [jobId]);

  return {
    connected,
    event,
    status,
    progress,
    stats,
    error,
  };
}
