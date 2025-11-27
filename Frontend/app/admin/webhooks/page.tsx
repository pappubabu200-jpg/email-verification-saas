"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function AdminWebhooksPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const loadEvents = async () => {
    try {
      const res = await axios.get("/admin/webhooks", {
        params: { page },
      });
      setEvents(res.data.events || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load webhooks");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEvents();

    if (!autoRefresh) return;

    const i = setInterval(loadEvents, 3000);
    return () => clearInterval(i);
  }, [page, autoRefresh]);

  if (loading) return <Loader />;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Webhook Events</h1>

        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto Refresh
          </label>

          <Button onClick={loadEvents}>Refresh</Button>
        </div>
      </div>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-100">
            <tr>
              <th className="p-3 text-left">ID</th>
              <th className="p-3 text-left">Type</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-left">Attempts</th>
              <th className="p-3 text-left">Endpoint</th>
              <th className="p-3 text-left">Created</th>
              <th className="p-3 text-left">Actions</th>
            </tr>
          </thead>

          <tbody>
            {events.map((e) => {
              const badge =
                e.status === "delivered"
                  ? "bg-green-100 text-green-700"
                  : e.status === "failed"
                  ? "bg-red-100 text-red-700"
                  : "bg-yellow-100 text-yellow-700";

              return (
                <tr key={e.id} className="border-b hover:bg-gray-50">
                  <td className="p-3">{e.id}</td>
                  <td className="p-3 font-medium">{e.event_type}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 rounded text-xs ${badge}`}>
                      {e.status.toUpperCase()}
                    </span>
                  </td>
                  <td className="p-3">{e.attempts}</td>
                  <td className="p-3 text-blue-600">{e.endpoint}</td>
                  <td className="p-3">
                    {new Date(e.created_at).toLocaleString()}
                  </td>
                  <td className="p-3">
                    {e.status === "failed" && (
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => retryWebhook(e.id)}
                      >
                        Retry
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-center gap-4">
        <Button disabled={page === 1} onClick={() => setPage(page - 1)}>
          Prev
        </Button>

        <span className="text-sm text-gray-600">Page {page}</span>

        <Button onClick={() => setPage(page + 1)}>Next</Button>
      </div>
    </div>
  );

  async function retryWebhook(id: string) {
    try {
      await axios.post(`/admin/webhooks/${id}/retry`);
      alert("Retry triggered.");
      loadEvents();
    } catch (err) {
      alert("Failed to retry webhook.");
    }
  }
}


// Frontend/app/admin/webhooks/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useAdminWebhooksWS } from "@/hooks/useAdminWebhooksWS";
import WebhookEventsTable from "@/components/Admin/WebhookEventsTable";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import axios from "@/lib/axios";

export default function AdminWebhooksPage() {
  const ws = useAdminWebhooksWS();
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [initialEvents, setInitialEvents] = useState<any[]>([]);
  const [filter, setFilter] = useState<"all" | "failed" | "delivered" | "pending">("all");

  useEffect(() => {
    async function loadRecent() {
      try {
        setLoadingInitial(true);
        const res = await axios.get("/admin/webhooks/recent"); // backend should expose recent events
        setInitialEvents(res.data.events || []);
      } catch (err) {
        console.error("Failed to load recent webhooks", err);
      } finally {
        setLoadingInitial(false);
      }
    }
    loadRecent();
  }, []);

  const combined = [...(ws.events || []), ...initialEvents].reduce((acc: any[], ev: any) => {
    // de-duplicate by id, keep newest first
    if (!acc.find((x) => x.id === ev.id)) acc.push(ev);
    return acc;
  }, []);

  const filtered = combined.filter((ev) => (filter === "all" ? true : ev.status === filter));

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Admin — Webhooks</h1>
          <p className="text-sm text-gray-500">Live webhook events & retry tools</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs text-gray-500">WS: {ws.connected ? "connected" : "disconnected"}</div>
          <Button onClick={() => ws.clearEvents()}>Clear</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="p-3">
          <div className="text-xs text-gray-500">Filter</div>
          <div className="flex gap-2 mt-2">
            <Button variant={filter === "all" ? "primary" : "secondary"} size="sm" onClick={() => setFilter("all")}>All</Button>
            <Button variant={filter === "failed" ? "primary" : "secondary"} size="sm" onClick={() => setFilter("failed")}>Failed</Button>
            <Button variant={filter === "delivered" ? "primary" : "secondary"} size="sm" onClick={() => setFilter("delivered")}>Delivered</Button>
            <Button variant={filter === "pending" ? "primary" : "secondary"} size="sm" onClick={() => setFilter("pending")}>Pending</Button>
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-xs text-gray-500">Summary</div>
          <div className="mt-2 text-sm">
            <div>Total shown: {filtered.length}</div>
            <div>WS events: {ws.events.length}</div>
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-xs text-gray-500">Actions</div>
          <div className="mt-2">
            <Button
              onClick={async () => {
                try {
                  await axios.post("/admin/webhooks/clear-failed");
                  alert("Requested clearing failed webhooks (backend action).");
                } catch (err) {
                  alert("Clearing failed webhooks request failed.");
                }
              }}
              size="sm"
              variant="secondary"
            >
              Clear failed
            </Button>
          </div>
        </Card>
      </div>

      {loadingInitial ? (
        <div className="p-6">
          <Loader />
        </div>
      ) : (
        <WebhookEventsTable
          events={filtered}
          onRetrySuccess={(id) => {
            // optimistic update - find and mark pending
            // (a more advanced approach would update by id in the WS state)
            // do quick UI feedback:
            // (no-op here)
            console.log("Retry requested for", id);
          }}
        />
      )}
    </div>
  );
}
