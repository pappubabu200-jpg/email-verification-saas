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
