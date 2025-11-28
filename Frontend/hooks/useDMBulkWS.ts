
// Frontend/hooks/useDMBulkWS.ts
import { useEffect, useState } from "react";

type Event = any;

export function useDMBulkWS(jobId?: string) {
  const [event, setEvent] = useState<Event | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const urlBase = process.env.NEXT_PUBLIC_WS_URL || (window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host;
    const ws = new WebSocket(`${urlBase}/ws/dm/bulk/${jobId}`);

    ws.onopen = () => console.debug("dm-bulk ws open", jobId);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setEvent(data);
      } catch (err) {
        console.error("ws parse error", err);
      }
    };
    ws.onclose = () => console.debug("dm-bulk ws closed");
    ws.onerror = (e) => console.error("dm-bulk ws error", e);

    return () => {
      try { ws.close(); } catch {}
    };
  }, [jobId]);

  return event;
}

export default useDMBulkWS;
