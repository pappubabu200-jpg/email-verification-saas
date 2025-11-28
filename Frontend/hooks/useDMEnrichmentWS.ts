"use client";

import { useEffect, useRef, useState } from "react";

interface DMEvent {
  event: string;
  dm_id: string;
  task_id?: string;
  step?: string;
  error?: string;
  enrichment_summary?: any;
}

export function useDMEnrichmentWS(dmId: string | null) {
  const [connected, setConnected] = useState(false);
  const [event, setEvent] = useState<DMEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!dmId) return;

    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}/ws/dm/${dmId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        setEvent(data);
      } catch {
        console.error("WS parse failed");
      }
    };

    ws.onclose = () => setConnected(false);
    ws.onerror = () => console.error("DM WS error");

    return () => ws.close();
  }, [dmId]);

  return {
    connected,
    event, // last websocket event
  };
}
