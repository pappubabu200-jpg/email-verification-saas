"use client";

import { useEffect, useRef, useState } from "react";

export function useAdminMetricsWS() {
  const wsRef = useRef<WebSocket | null>(null);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const url = `${process.env.NEXT_PUBLIC_WS_URL}/ws/admin/metrics`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.event === "metrics") {
        setData(msg);
      }
    };

    ws.onerror = () => console.error("Admin WS error");
    ws.onclose = () => console.warn("Admin WS closed, reconnecting…");

    return () => ws.close();
  }, []);

  return data; // live push
}

// Frontend/hooks/useAdminWebhooksWS.ts
"use client";

import { useEffect, useRef, useState } from "react";

type WebhookEvent = {
  id: string;
  ts: string;
  endpoint: string;
  payload_preview?: string;
  status: "delivered" | "failed" | "pending";
  attempts?: number;
  last_error?: string | null;
  source?: string | null;
};

type HookState = {
  connected: boolean;
  events: WebhookEvent[];
  lastMessage?: any;
};

const DEFAULT_MAX_EVENTS = 200;

/**
 * useAdminWebhooksWS
 * - Connects to admin websocket for webhook events
 * - Reconnects with exponential backoff
 * - Maintains a bounded list of recent events
 */
export function useAdminWebhooksWS(opts?: { url?: string; maxEvents?: number }) {
  const wsUrl =
    opts?.url ||
    (typeof window !== "undefined" && process.env.NEXT_PUBLIC_ADMIN_WS_URL) ||
    (typeof window !== "undefined" && `${window.location.origin.replace(/^http/, "ws")}/ws/admin/webhooks`);

  const maxEvents = opts?.maxEvents || DEFAULT_MAX_EVENTS;
  const [state, setState] = useState<HookState>({ connected: false, events: [] });
  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(1000); // start 1s
  const shouldReconnectRef = useRef<boolean>(true);
  const pingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    shouldReconnectRef.current = true;

    function connect() {
      try {
        if (!wsUrl) return;
        wsRef.current = new WebSocket(wsUrl);

        wsRef.current.onopen = () => {
          backoffRef.current = 1000; // reset
          setState((s) => ({ ...s, connected: true }));
          // start ping (if server expects)
          if (pingTimerRef.current) window.clearInterval(pingTimerRef.current);
          pingTimerRef.current = window.setInterval(() => {
            try {
              wsRef.current?.send(JSON.stringify({ type: "ping" }));
            } catch {}
          }, 25_000);
        };

        wsRef.current.onmessage = (ev) => {
          try {
            const payload = JSON.parse(ev.data);
            // Expect messages: { type: "webhook_event", data: {...} }
            if (payload?.type === "webhook_event" && payload?.data) {
              const item: WebhookEvent = payload.data;
              setState((s) => {
                const next = [item, ...s.events].slice(0, maxEvents);
                return { ...s, events: next, lastMessage: payload };
              });
            } else {
              // store raw message
              setState((s) => ({ ...s, lastMessage: payload }));
            }
          } catch (e) {
            // ignore parse errors
            console.error("WS parse error", e);
          }
        };

        wsRef.current.onerror = (err) => {
          console.error("Admin webhooks WS error", err);
        };

        wsRef.current.onclose = (ev) => {
          setState((s) => ({ ...s, connected: false }));
          if (pingTimerRef.current) {
            window.clearInterval(pingTimerRef.current);
            pingTimerRef.current = null;
          }
          if (shouldReconnectRef.current) {
            const backoff = backoffRef.current;
            backoffRef.current = Math.min(backoffRef.current * 1.8, 30_000);
            setTimeout(connect, backoff);
          }
        };
      } catch (e) {
        console.error("WS connect failed", e);
      }
    }

    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (pingTimerRef.current) window.clearInterval(pingTimerRef.current);
      try {
        wsRef.current?.close();
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsUrl, maxEvents]);

  // helper to clear events
  const clearEvents = () => setState((s) => ({ ...s, events: [] }));

  // helper to push a synthetic event (useful for testing)
  const pushEvent = (ev: WebhookEvent) =>
    setState((s) => ({ ...s, events: [ev, ...s.events].slice(0, maxEvents) }));

  return {
    connected: state.connected,
    events: state.events,
    lastMessage: state.lastMessage,
    clearEvents,
    pushEvent,
  };
  }

