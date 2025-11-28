// frontend/hooks/useVerificationWS.ts
"use client";

import { useEffect, useRef, useState } from "react";

// --- Type Definitions for Clarity ---

// Define the shape of a generic event coming from the server
type VerificationEvent = {
  event: string; // e.g., "credits", "verification", "bulk_progress"
  job_id?: string;
  user_id?: string | number;
  remaining?: number; // for "credits"
  value?: number; // for "credits"
  remaining_credits?: number; // for "credits"
  result?: any; // for "verification"
  processed?: number; // for "bulk_progress"
  total?: number; // for "bulk_progress"
  stats?: any; // for "bulk_progress"
  deliverability?: any; // for "deliverability"
  [key: string]: any; // Allow other properties
};

// Define the shape of the data returned by the hook
type HookReturnType = {
  connected: boolean;
  lastEvent: VerificationEvent | null;
  credits: number | null;
  verificationsSeries: { ts: string; count: number }[];
  deliverability: any;
  events: VerificationEvent[]; // Array of all recent events
};

// --- Hook Implementation ---

export function useVerificationWS(userId?: string | number | null): HookReturnType {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<VerificationEvent | null>(null);
  const [credits, setCredits] = useState<number | null>(null);
  // Simple series for charting/dashboard visibility
  const [verificationsSeries, setVerificationsSeries] = useState<{ ts: string; count: number }[]>([]);
  const [deliverability, setDeliverability] = useState<any>(null);
  // General chronological list of recent events
  const [events, setEvents] = useState<VerificationEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  // Ref to hold the current userId state safely within the interval/timeout closures
  const userIdRef = useRef(userId);
  userIdRef.current = userId;

  useEffect(() => {
    if (!userIdRef.current) return;

    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;

    const connect = (currentAttempt: number) => {
      if (!userIdRef.current) return;

      const token =
        (typeof window !== "undefined" && localStorage.getItem("access_token")) || "";

      // Determine the base URL (wss or ws)
      const wsUrlBase =
        process.env.NEXT_PUBLIC_WS_URL ||
        (window.location.protocol === "https:" ? "wss" : "ws") +
          "://" +
          window.location.host;
      
      // Construct the full URL, passing the token as a query parameter
      const headersQuery = token ? `?token=${encodeURIComponent(token)}` : "";
      const wsUrl = `${wsUrlBase}/ws/verification/${userIdRef.current}${headersQuery}`;


      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        attempt = 0; // Reset attempts on success
        console.debug(`Verification WS connected for user ${userIdRef.current}`);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          const payload: VerificationEvent = msg.payload || msg;

          setLastEvent(payload);

          // --- Event Handling ---
          if (payload.event === "credits") {
            const creditValue = Number(payload.remaining || payload.value || payload.remaining_credits || 0);
            if (!isNaN(creditValue)) {
              setCredits(creditValue);
            }
          } else if (payload.event === "verification") {
            // New instant verification result
            setEvents(prev => [payload].concat(prev).slice(0, 50));
            setVerificationsSeries(prev => {
              const ts = new Date().toISOString();
              return prev.concat([{ ts, count: 1 }]).slice(-50); // Keep last 50 data points
            });
          } else if (
            payload.event === "bulk_progress" || 
            payload.event === "bulk_completed" || 
            payload.event === "bulk_failed"
          ) {
            // Bulk job update (from worker via Redis)
            setEvents(prev => [payload].concat(prev).slice(0, 200));
          } else if (payload.event === "deliverability") {
            setDeliverability(payload);
          } else {
            // Generic event push
            setEvents(prev => [payload].concat(prev).slice(0, 200));
          }
        } catch (err) {
          console.error("Invalid WS message format:", ev.data, err);
        }
      };

      ws.onerror = (e) => {
        console.error("Verification WS error:", e);
      };

      ws.onclose = () => {
        setConnected(false);
        console.debug(`Verification WS closed for user ${userIdRef.current}`);
        
        // Attempt Reconnect
        if (userIdRef.current && currentAttempt < MAX_RECONNECT_ATTEMPTS) {
          attempt = currentAttempt + 1;
          const backoffTime = Math.min(3000 * Math.pow(2, currentAttempt), 30000); // 3s, 6s, 12s, 24s, 30s
          
          console.debug(`Attempting reconnect in ${backoffTime / 1000}s (Attempt ${attempt})`);
          
          reconnectTimeout = setTimeout(() => {
            connect(attempt);
          }, backoffTime);
        } else if (userIdRef.current) {
             console.error(`Exceeded max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}). Stopping.`);
        }
      };
    };

    // Start the initial connection
    connect(attempt);

    // --- Cleanup ---
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (wsRef.current) {
        try {
          wsRef.current.onclose = null; // Prevent reconnect on intentional close
          wsRef.current.close();
        } catch (e) {
          console.error("Error closing WS", e);
        }
      }
      wsRef.current = null;
    };
  }, [userId]); // Re-run effect only when userId changes

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
