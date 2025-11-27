"use client";

import { useEffect, useState, useMemo } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

// Recharts components (should be in your frontend dependencies)
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";

function SmallStat({ title, value, hint }: { title: string; value: string | number; hint?: string }) {
  return (
    <div className="p-4 rounded border bg-white">
      <div className="text-xs text-gray-500">{title}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-xs text-gray-400 mt-1">{hint}</div>}
    </div>
  );
}

export default function AdminDashboardsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Data
  const [credits, setCredits] = useState<{ remaining: number; reserved: number } | null>(null);
  const [lastVerificationsSeries, setLastVerificationsSeries] = useState<Array<any>>([]);
  const [deliverability, setDeliverability] = useState<{ score: number; trend: number } | null>(null);
  const [recentEvents, setRecentEvents] = useState<Array<any>>([]);

  // load everything
  const loadAll = async () => {
    setError(null);
    setLoading(true);
    try {
      const [cRes, vRes, dRes, rRes] = await Promise.all([
        axios.get("/admin/analytics/credits"), // { remaining, reserved }
        axios.get("/admin/analytics/last_verifications"), // { series: [{ts, count}, ...] }
        axios.get("/admin/analytics/deliverability"), // { score: 93.2, trend: -0.4 }
        axios.get("/admin/analytics/recent_actions"), // { events: [...] }
      ]);

      setCredits(cRes.data || null);
      setLastVerificationsSeries((vRes.data && vRes.data.series) || []);
      setDeliverability(dRes.data || null);
      setRecentEvents((rRes.data && rRes.data.events) || []);
    } catch (err: any) {
      console.error("Admin dashboard load failed", err);
      setError(err?.response?.data?.detail || "Failed to load admin analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
    if (!autoRefresh) return;

    const id = setInterval(loadAll, 5000);
    return () => clearInterval(id);
  }, [autoRefresh]);

  // derived values for charts
  const verificationsChart = useMemo(() => {
    // Expect series: [{ts: "2025-11-26T10:00:00Z", count: 120}, ...]
    return lastVerificationsSeries.map((p: any) => ({
      time: new Date(p.ts).toLocaleTimeString(),
      count: p.count,
    }));
  }, [lastVerificationsSeries]);

  if (loading) return <div className="p-8"><Loader /></div>;
  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Admin Dashboard</h1>
          <p className="text-sm text-gray-500">Overview: Live metrics, usage and deliverability.</p>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto-refresh
          </label>
          <Button onClick={loadAll}>Refresh</Button>
        </div>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SmallStat
          title="Credits Remaining (global)"
          value={credits ? credits.remaining.toLocaleString() : "—"}
          hint={`Reserved: ${credits ? credits.reserved.toLocaleString() : "—"}`}
        />
        <div className="p-4 rounded border bg-white">
          <div className="flex justify-between items-center">
            <div>
              <div className="text-xs text-gray-500">Deliverability Score</div>
              <div className="text-3xl font-semibold mt-1">
                {deliverability ? `${Math.round(deliverability.score)}%` : "—"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Trend: {deliverability ? `${deliverability.trend >= 0 ? "+" : ""}${deliverability.trend}%` : "—"}
              </div>
            </div>

            {/* simple circular gauge */}
            <div style={{ width: 86, height: 86 }} className="flex items-center justify-center">
              <svg viewBox="0 0 36 36" className="w-20 h-20">
                <path
                  d="M18 2.0845
                     a 15.9155 15.9155 0 0 1 0 31.831
                     a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="#e5e7eb"
                  strokeWidth="2.8"
                />
                <path
                  d="M18 2.0845
                     a 15.9155 15.9155 0 0 1 0 31.831"
                  fill="none"
                  stroke={deliverability && deliverability.score > 90 ? "#16a34a" : deliverability && deliverability.score > 70 ? "#f59e0b" : "#ef4444"}
                  strokeWidth="2.8"
                  strokeDasharray={`${deliverability ? deliverability.score : 0}, 100`}
                />
                <text x="18" y="20" textAnchor="middle" fontSize="6" fill="#111827">
                  {deliverability ? `${Math.round(deliverability.score)}` : "--"}%
                </text>
              </svg>
            </div>
          </div>
        </div>

        <SmallStat title="Last 24h Verifications" value={lastVerificationsSeries.reduce((s: number, p: any) => s + (p.count || 0), 0)} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold">Verifications (recent)</h3>
            <div className="text-xs text-gray-500">last points</div>
          </div>

          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={verificationsChart}>
                <XAxis dataKey="time" minTickGap={20} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold">Deliverability breakdown</h3>
            <div className="text-xs text-gray-500">valid | risky | invalid</div>
          </div>

          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={[
                { name: "valid", value: (lastVerificationsSeries && lastVerificationsSeries.slice(-1)[0]?.valid) || 0 },
                { name: "risky", value: (lastVerificationsSeries && lastVerificationsSeries.slice(-1)[0]?.risky) || 0 },
                { name: "invalid", value: (lastVerificationsSeries && lastVerificationsSeries.slice(-1)[0]?.invalid) || 0 },
              ]}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value">
                  <Cell fill="#16a34a" />
                  <Cell fill="#f59e0b" />
                  <Cell fill="#ef4444" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Recent actions table */}
      <Card className="p-0 overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="text-sm font-semibold">Recent Actions</h3>
          <div className="text-xs text-gray-500">live feed</div>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-3 text-left">Time</th>
              <th className="p-3 text-left">Type</th>
              <th className="p-3 text-left">Target</th>
              <th className="p-3 text-left">Outcome</th>
              <th className="p-3 text-left">Source</th>
            </tr>
          </thead>
          <tbody>
            {recentEvents.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-gray-500">No recent events</td>
              </tr>
            )}

            {recentEvents.map((ev: any, idx: number) => (
              <tr key={idx} className="border-b hover:bg-gray-50">
                <td className="p-3">{new Date(ev.ts).toLocaleString()}</td>
                <td className="p-3 font-medium">{ev.type}</td>
                <td className="p-3">{ev.target || "-"}</td>
                <td className="p-3">{ev.outcome || "-"}</td>
                <td className="p-3 text-xs text-gray-500">{ev.source || "system"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
