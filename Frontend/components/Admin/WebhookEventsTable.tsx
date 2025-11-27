// Frontend/components/Admin/WebhookEventsTable.tsx
"use client";

import React, { useState } from "react";
import axios from "@/lib/axios";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";

type WebhookEvent = {
  id: string;
  ts: string;
  endpoint: string;
  payload_preview?: string;
  status: "delivered" | "failed" | "pending";
  attempts?: number;
  last_error?: string | null;
  source?: string | null;
};

export default function WebhookEventsTable({
  events,
  onRetrySuccess,
}: {
  events: WebhookEvent[];
  onRetrySuccess?: (id: string) => void;
}) {
  const [retrying, setRetrying] = useState<Record<string, boolean>>({});

  const handleRetry = async (id: string) => {
    setRetrying((r) => ({ ...r, [id]: true }));
    try {
      await axios.post(`/admin/webhooks/${id}/retry`);
      if (onRetrySuccess) onRetrySuccess(id);
    } catch (err: any) {
      console.error("Retry failed", err);
      alert(err?.response?.data?.detail || "Retry failed");
    } finally {
      setRetrying((r) => ({ ...r, [id]: false }));
    }
  };

  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b flex items-center justify-between">
        <h3 className="text-sm font-semibold">Webhook Events</h3>
        <div className="text-xs text-gray-500">live</div>
      </div>

      <div className="w-full overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-3 text-left">Time</th>
              <th className="p-3 text-left">Endpoint</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-left">Attempts</th>
              <th className="p-3 text-left">Preview</th>
              <th className="p-3 text-left">Actions</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-gray-500">
                  No webhook events yet
                </td>
              </tr>
            )}

            {events.map((ev) => (
              <tr key={ev.id} className="border-b hover:bg-gray-50">
                <td className="p-3">{new Date(ev.ts).toLocaleString()}</td>
                <td className="p-3 break-all max-w-xs">{ev.endpoint}</td>
                <td className="p-3">
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      ev.status === "delivered"
                        ? "bg-green-100 text-green-700"
                        : ev.status === "failed"
                        ? "bg-red-100 text-red-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}
                  >
                    {ev.status.toUpperCase()}
                  </span>
                </td>
                <td className="p-3">{ev.attempts ?? 0}</td>
                <td className="p-3">
                  <div className="text-xs text-gray-600 max-w-lg truncate">
                    {ev.payload_preview ?? "-"}
                  </div>
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        // open endpoint in new tab (admin convenience)
                        window.open(ev.endpoint, "_blank");
                      }}
                    >
                      Open
                    </Button>

                    {ev.status === "failed" && (
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() => handleRetry(ev.id)}
                        disabled={!!retrying[ev.id]}
                      >
                        {retrying[ev.id] ? "Retrying..." : "Retry"}
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
