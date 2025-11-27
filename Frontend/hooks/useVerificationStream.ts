
"use client";

import { useEffect, useRef, useState } from "react";

type VerificationEvent =
  | {
      event: "credits";
      remaining: number;
      reserved: number;
    }
  | {
      event: "single_verification";
      email: string;
      status: string;
      score: number;
      reason?: string;
      ts: string;
    }
  | {
      event: "risk_chart_update";
      buckets: {
        valid: number;
        risky: number;
        invalid: number;
        unknown: number;
      };
    }
  | {
      event: "bulk_progress";
      job_id: string;
      processed: number;
      total: number;
      stats: {
        valid: number;
        invalid: number;
        remaining: number;
      };
    }
  | {
      event: "bulk_completed";
      job_id: string;
      processed: number;
      total: number;
      stats: {
        valid: number;
        invalid: number;
      };
    }
  | {
      event: "bulk_failed";
      job_id: string;
      error: string;
    }
  | {
      event: "feed";
      message: string;
      ts: string;
    };

export function useVerificationStream(userId: string | number | undefined) {
  const wsRef = useRef<WebSocket | null>(null);

  // --- STATE HOLDERS ---
  const [credits, setCredits] = useState<{ remaining: number; reserved: number } | null>(null);
  const [lastVerification, setLastVerification] = useState<any>(null);
  const [riskChart, setRiskChart] = useState<any>({
    valid: 0,
    risky: 0,
    invalid: 0,
    unknown: 0,
  });

  const [bulkJobs, setBulkJobs] = useState<Record<string, any>>({});
  const [events, setEvents] = useState<any[]>([]);

  useEffect(() => {
    if (!userId) return;

    const WS_URL = process.env.NEXT_PUBLIC_WS_URL;
    if (!WS_URL) {
      console.error("NEXT_PUBLIC_WS_URL missing");
      return;
    }

    const ws = new WebSocket(`${WS_URL}/ws/verify/${userId}`);
    wsRef.current = ws;

    ws.onopen = () => console.log("WS: verification connected");
    ws.onerror = (e) => console.error("WS error", e);

    ws.onmessage = (msg) => {
      try {
        const data: VerificationEvent = JSON.parse(msg.data);

        // Handle all event types
        switch (data.event) {
          case "credits":
            setCredits({
              remaining: data.remaining,
              reserved: data.reserved,
            });
            break;

          case "single_verification":
            setLastVerification({
              email: data.email,
              status: data.status,
              score: data.score,
              reason: data.reason,
              ts: data.ts,
            });

            // Push to events feed
            setEvents((e) => [
              { type: "verification", email: data.email, status: data.status, ts: data.ts },
              ...e,
            ]);
            break;

          case "risk_chart_update":
            setRiskChart(data.buckets);
            break;

          case "bulk_progress":
            setBulkJobs((prev) => ({
              ...prev,
              [data.job_id]: {
                ...prev[data.job_id],
                ...data,
              },
            }));

            setEvents((e) => [
              {
                type: "bulk_progress",
                job_id: data.job_id,
                processed: data.processed,
                total: data.total,
                ts: new Date().toISOString(),
              },
              ...e,
            ]);
            break;

          case "bulk_completed":
            setBulkJobs((prev) => ({
              ...prev,
              [data.job_id]: {
                ...prev[data.job_id],
                status: "completed",
                ...data,
              },
            }));

            setEvents((e) => [
              {
                type: "bulk_completed",
                job_id: data.job_id,
                ts: new Date().toISOString(),
              },
              ...e,
            ]);
            break;

          case "bulk_failed":
            setBulkJobs((prev) => ({
              ...prev,
              [data.job_id]: {
                ...prev[data.job_id],
                status: "failed",
              },
            }));
            break;

          case "feed":
            setEvents((e) => [
              { type: "event", message: data.message, ts: data.ts },
              ...e,
            ]);
            break;

          default:
            console.warn("Unknown WS event:", data);
        }
      } catch (err) {
        console.error("WS parse error:", err);
      }
    };

    ws.onclose = () => console.log("WS: closed");

    return () => ws.close();
  }, [userId]);

  return {
    credits,
    lastVerification,
    riskChart,
    bulkJobs,
    events,
  };
}

export default useVerificationStream;
