// Frontend/hooks/useAdminAPILogWS.ts
import { useEffect, useRef, useState } from "react";

export function useAdminAPILogWS(url?: string) {
  const [messages, setMessages] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl = url || `${process.env.NEXT_PUBLIC_WS_URL || ""}/ws/admin/apilogs`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("Admin API log WS connected");
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        // keep only latest 500 messages
        setMessages((prev) => {
          const out = [data, ...prev];
          if (out.length > 500) out.pop();
          return out;
        });
      } catch (e) {
        console.error("Invalid ws message", e);
      }
    };

    ws.onerror = (err) => {
      console.error("Admin API log WS error", err);
    };

    ws.onclose = () => {
      console.log("Admin API log WS closed");
      // try reconnect after small delay
      setTimeout(() => {
        // simple reconnect: re-run effect by toggling a key (not implemented here).
      }, 2000);
    };

    return () => {
      try {
        ws.close();
      } catch {}
    };
  }, [url]);

  return { messages, ws: wsRef.current };
    }
