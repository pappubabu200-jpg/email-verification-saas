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
