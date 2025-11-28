
"use client";

import { useEffect, useState } from "react";

export function useBulkWS(jobId: string) {
  const [event, setEvent] = useState<any>(null);

  useEffect(() => {
    if (!jobId) return;

    const ws = new WebSocket(
      `${process.env.NEXT_PUBLIC_WS_URL}/ws/bulk/${jobId}`
    );

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setEvent(data);
      } catch (e) {
        console.error("WS parse error", e);
      }
    };

    ws.onerror = (e) => console.error("WS error", e);
    ws.onclose = () => console.log("Bulk WS closed");

    return () => ws.close();
  }, [jobId]);

  return event;
}
