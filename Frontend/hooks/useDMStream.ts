import { useEffect, useRef, useState } from "react";

export default function useDMStream() {
  const [updates, setUpdates] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const url = (process.env.NEXT_PUBLIC_WS_URL || window.location.origin.replace(/^http/, "ws")) + "/ws/dm/stream";
    const ws = new WebSocket(url);

    ws.onopen = () => console.log("DM WS connected");
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        // expect messages like { type: "enrichment", id, email, ... }
        setUpdates((prev) => [...prev, data].slice(-200)); // keep last 200
      } catch (e) {
        console.error("WS parse error", e);
      }
    };
    ws.onerror = (e) => console.error("DM WS error", e);
    ws.onclose = () => console.log("DM WS closed");

    wsRef.current = ws;
    return () => {
      try {
        ws.close();
      } catch {}
    };
  }, []);

  return { updates, ws: wsRef.current };
}
