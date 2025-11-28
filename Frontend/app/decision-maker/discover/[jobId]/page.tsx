// Frontend/app/decision-maker/discover/[jobId]/page.tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import { useDmDiscoveryStream } from "@/hooks/useDmDiscoveryStream";
import axios from "@/lib/axios";

export default function DMDiscoverJobPage() {
  const { jobId } = useParams();
  const router = useRouter();

  const { connected, events, reset } = useDmDiscoveryStream(jobId);

  const [items, setItems] = useState<any[]>([]);
  const [added, setAdded] = useState<number>(0);
  const [status, setStatus] = useState<string>("queued");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // fold events into UI state
    for (const ev of events.slice(items.length ? 0 : 0)) {
      if (!ev) continue;
      if (ev.event === "discover_progress") {
        setAdded(ev.added ?? added);
        if (ev.latest) {
          setItems((prev) => {
            // avoid dupes by email or name
            const key = ev.latest.email || ev.latest.name;
            if (prev.find((p) => (p.email || p.name) === key)) return prev;
            return [...prev, ev.latest];
          });
        }
      } else if (ev.event === "discover_item") {
        setItems((prev) => {
          const key = ev.item?.email || ev.item?.name;
          if (prev.find((p) => (p.email || p.name) === key)) return prev;
          return [...prev, ev.item];
        });
      } else if (ev.event === "discover_check") {
        // ignore
      } else if (ev.event === "discover_completed") {
        setStatus("completed");
      } else if (ev.event === "discover_failed") {
        setStatus("failed");
        setError(ev.error || "Discovery failed");
      } else if (ev.event === "discover_started") {
        setStatus("running");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  // convenience: API to start a new discover (if user is on a starter page)
  const startAnother = async () => {
    // example: POST /dm/discover { domain: "example.com" } -> { job_id }
    try {
      const res = await axios.post("/dm/discover", { domain: "example.com", max_results: 50 });
      router.push(`/decision-maker/discover/${res.data.job_id}`);
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to start discover");
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Discovery Job</h1>
          <p className="text-sm text-gray-500">Job ID: <code>{jobId}</code></p>
        </div>

        <div className="flex items-center gap-3">
          <div className={`text-sm ${connected ? "text-green-600" : "text-gray-500"}`}>
            {connected ? "Live" : "Disconnected"}
          </div>
          <Button onClick={() => reset()}>Clear</Button>
          <Button onClick={startAnother} variant="secondary">Start demo job</Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <Card>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">Status</p>
            <div className="font-semibold text-lg">{status.toUpperCase()}</div>
          </div>

          <div>
            <p className="text-sm text-gray-500">Discovered</p>
            <div className="text-xl font-bold">{items.length}</div>
          </div>

          <div>
            <p className="text-sm text-gray-500">Added (stream)</p>
            <div className="text-xl font-bold">{added}</div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {items.map((it, idx) => (
          <Card key={idx} className="p-4">
            <div className="flex items-start gap-4">
              <div className="rounded-full bg-gray-200 h-12 w-12 flex items-center justify-center text-xl">
                {it.name ? it.name.charAt(0) : "?"}
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <div className="font-semibold">{it.name || `${it.first_name || ""} ${it.last_name || ""}`}</div>
                  {it.verified && <div className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">verified</div>}
                </div>
                <div className="text-sm text-gray-500">{it.title || "-"}</div>
                <div className="text-xs text-gray-600 mt-2">
                  <strong>Email:</strong> {it.email || (it.guesses && it.guesses[0] && it.guesses[0].email) || "—"}
                </div>
                <div className="text-xs text-gray-400 mt-1">{it.company || it.domain || "-"}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {status !== "completed" && (
        <div className="text-center">
          <Loader />
          <div className="text-sm text-gray-500 mt-2">Waiting for more items...</div>
        </div>
      )}
    </div>
  );
}
