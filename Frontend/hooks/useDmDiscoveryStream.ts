// Frontend/hooks/useDmDiscoveryStream.ts
"use client";

import { useEffect, useRef, useState } from "react";

type DMEvent =
  | { event: "discover_progress"; added: number; latest?: any }
  | { event: "discover_item"; item: any }
  | { event: "discover_check"; index: number; person?: any }
  | { event: "discover_completed"; count: number }
  | { event: "discover_failed"; error?: string }
  | any;

export function useDmDiscoveryStream(jobId?: string) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<DMEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number>(0);

  useEffect(() => {
    if (!jobId) return;

    let shouldStop = false;
    const urlBase = process.env.NEXT_PUBLIC_WS_URL || (typeof window !== "undefined" ? window.location.origin.replace(/^http/, "ws") : "");
    const wsUrl = `${urlBase.replace(/\/$/, "")}/ws/dm/job/${encodeURIComponent(jobId)}`;

    function connect() {
      try {
        wsRef.current = new WebSocket(wsUrl);
      } catch (err) {
        console.error("WS connect error", err);
        scheduleReconnect();
        return;
      }

      wsRef.current.onopen = () => {
        setConnected(true);
        reconnectRef.current = 0;
      };

      wsRef.current.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          setEvents((prev) => [...prev, data]);
        } catch (err) {
          console.warn("Invalid WS payload", err);
        }
      };

      wsRef.current.onclose = () => {
        setConnected(false);
        if (!shouldStop) scheduleReconnect();
      };

      wsRef.current.onerror = (err) => {
        console.error("WS error", err);
        try {
          wsRef.current?.close();
        } catch {}
      };
    }

    function scheduleReconnect() {
      reconnectRef.current = Math.min(30000, reconnectRef.current ? reconnectRef.current * 2 : 1000);
      const delay = reconnectRef.current || 1000;
      setTimeout(() => {
        if (!shouldStop) connect();
      }, delay);
    }

    connect();

    return () => {
      shouldStop = true;
      try {
        wsRef.current?.close();
      } catch {}
      wsRef.current = null;
      setConnected(false);
    };
  }, [jobId]);

  // helper to reset events
  const reset = () => setEvents([]);

  return {
    connected,
    events,
    reset,
    rawSocket: wsRef.current,
  };
}
