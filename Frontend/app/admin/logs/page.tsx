"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";

export default function AdminLogsPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const res = await axios.get("/admin/logs");
      setLogs(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) return <Loader />;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-semibold mb-4">Audit Logs</h1>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="p-3">Time</th>
              <th className="p-3">User</th>
              <th className="p-3">Action</th>
              <th className="p-3">IP</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-b">
                <td className="p-3">{new Date(l.timestamp).toLocaleString()}</td>
                <td className="p-3">{l.user_email}</td>
                <td className="p-3">{l.action}</td>
                <td className="p-3">{l.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

"use client";

import { useMemo } from "react";
import { useAdminAPILogWS } from "@/hooks/useAdminAPILogWS";
import Card from "@/components/ui/Card";

export default function AdminApiLogsPage() {
  const { messages } = useAdminAPILogWS();

  const rows = useMemo(() => messages.slice(0, 200), [messages]);

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Live API Logs</h1>
        <p className="text-sm text-gray-500">Incoming requests (admin only)</p>
      </div>

      <Card>
        <div className="overflow-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="p-2 text-left">Time</th>
                <th className="p-2 text-left">Method</th>
                <th className="p-2 text-left">Path</th>
                <th className="p-2 text-left">Status</th>
                <th className="p-2 text-left">Duration (ms)</th>
                <th className="p-2 text-left">Client</th>
                <th className="p-2 text-left">User / Key</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m: any, i: number) => (
                <tr key={i} className="border-b hover:bg-gray-50">
                  <td className="p-2">{m.ts ? new Date(m.ts * 1000).toLocaleTimeString() : "-"}</td>
                  <td className="p-2 font-medium">{m.method}</td>
                  <td className="p-2">{m.path}{m.query ? `?${m.query}` : ""}</td>
                  <td className="p-2">{m.status}</td>
                  <td className="p-2">{m.duration_ms}</td>
                  <td className="p-2">{m.client_ip || "-"}</td>
                  <td className="p-2 text-xs text-gray-600">{m.user_id || m.api_key_hint || "-"}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-gray-500">No logs yet</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
