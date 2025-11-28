// frontend/hooks/useVerificationWS.ts
"use client";

import { useEffect, useRef, useState } from "react";

type VerificationEvent = {
  from?: string;
  payload?: any;
};

export function useVerificationWS(userId?: string | number | null) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<VerificationEvent | null>(null);
  const [credits, setCredits] = useState<number | null>(null);
  const [verificationsSeries, setVerificationsSeries] = useState<any[]>([]);
  const [deliverability, setDeliverability] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!userId) return;

    const token = (typeof window !== "undefined" && localStorage.getItem("access_token")) || "";

    const wsUrlBase = process.env.NEXT_PUBLIC_WS_URL || (window.location.protocol === "https:" ? "wss" : "ws") + "://" + window.location.host;
    const wsUrl = `${wsUrlBase}/ws/verification/${userId}`;

    const headersQuery = token ? `?token=${encodeURIComponent(token)}` : "";

    const ws = new WebSocket(`${wsUrl}${headersQuery}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.debug("Verification WS connected");
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        const payload = msg.payload || msg;
        setLastEvent({ from: msg.from, payload });

        // handle well-known event shapes
        const p = payload;
        // Example payloads:
        // { event: "credits", remaining: 123 }
        // { event: "bulk_progress", job_id, processed, total, stats }
        // { event: "verification", result: {email, status, score} }
        if (p.event === "credits") {
          setCredits(Number(p.remaining || p.value || p.remaining_credits || 0));
        } else if (p.event === "verification") {
          // append to recent events
          setEvents(prev => [p].concat(prev).slice(0, 50));
          // optionally update verification series
          setVerificationsSeries(prev => {
            const ts = new Date().toISOString();
            return prev.concat([{ ts, count: 1 }]).slice(-50);
          });
        } else if (p.event === "bulk_progress" || p.event === "bulk_completed") {
          // surface progress to event list
          setEvents(prev => [p].concat(prev).slice(0, 200));
        } else if (p.event === "deliverability") {
          setDeliverability(p);
        } else {
          // generic push into events array
          setEvents(prev => [p].concat(prev).slice(0, 200));
        }
      } catch (err) {
        console.error("Invalid WS message", err);
      }
    };

    ws.onerror = (e) => {
      console.error("Verification WS error", e);
    };

    ws.onclose = () => {
      setConnected(false);
      console.debug("Verification WS closed");
      // try reconnect with backoff
      // simple reconnect: attempt after 3s
      setTimeout(() => {
        if (wsRef.current === ws) {
          // re-create by changing userId dependency (we'll simply set wsRef to null and let effect re-run)
          wsRef.current = null;
        }
      }, 3000);
    };

    return () => {
      try {
        ws.close();
      } catch (e) {}
      wsRef.current = null;
    };
  }, [userId]);

  return {
    connected,
    lastEvent,
    credits,
    verificationsSeries,
    deliverability,
    events,
  };
}

export default useVerificationWS;
