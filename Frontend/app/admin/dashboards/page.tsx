"use client";

import { useMemo } from "react";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";
import { useAdminMetricsWS } from "@/hooks/useAdminMetricsWS";

// Recharts
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

function SmallStat({
  title,
  value,
  hint,
}: {
  title: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="p-4 rounded border bg-white">
      <div className="text-xs text-gray-500">{title}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-xs text-gray-400 mt-1">{hint}</div>}
    </div>
  );
}

export default function AdminDashboardsPage() {
  // 🔥 REALTIME WebSocket stream
  const ws = useAdminMetricsWS();

  const credits = ws?.credits || null;
  const lastVerificationsSeries = ws?.verifications || [];
  const deliverability = ws?.deliverability || null;
  const recentEvents = ws?.events || [];

  // If WS not yet connected
  if (!ws)
    return (
      <div className="p-8 flex justify-center">
        <Loader />
      </div>
    );

  // derived values for charts
  const verificationsChart = useMemo(() => {
    return lastVerificationsSeries.map((p: any) => ({
      time: new Date(p.ts).toLocaleTimeString(),
      count: p.count,
    }));
  }, [lastVerificationsSeries]);

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Admin Dashboard</h1>
          <p className="text-sm text-gray-500">Live metrics & analytics (WebSocket powered)</p>
        </div>

        <Button onClick={() => location.reload()}>Reload</Button>
      </div>

      {/* TOP METRICS */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SmallStat
          title="Credits Remaining (global)"
          value={credits ? credits.remaining.toLocaleString() : "—"}
          hint={`Reserved: ${credits ? credits.reserved.toLocaleString() : "—"}`}
        />

        {/* Deliverability Circle */}
        <div className="p-4 rounded border bg-white">
          <div className="flex justify-between items-center">
            <div>
              <div className="text-xs text-gray-500">Deliverability Score</div>
              <div className="text-3xl font-semibold mt-1">
                {deliverability ? `${Math.round(deliverability.score)}%` : "—"}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Trend:{" "}
                {deliverability
                  ? `${deliverability.trend >= 0 ? "+" : ""}${deliverability.trend}%`
                  : "—"}
              </div>
            </div>

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
                  stroke={
                    deliverability && deliverability.score > 90
                      ? "#16a34a"
                      : deliverability && deliverability.score > 70
                      ? "#f59e0b"
                      : "#ef4444"
                  }
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

        <SmallStat
          title="Last 24h Verifications"
          value={lastVerificationsSeries.reduce(
            (s: number, p: any) => s + (p.count || 0),
            0
          )}
        />
      </div>

      {/* CHARTS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Line Chart */}
        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold">Verifications (recent)</h3>
          </div>

          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={verificationsChart}>
                <XAxis dataKey="time" minTickGap={20} />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Deliverability Breakdown */}
        <Card className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold">Deliverability Breakdown</h3>
          </div>

          <div style={{ height: 220 }}>
            <ResponsiveContainer>
              <BarChart
                data={[
                  { name: "valid", value: ws?.lastPoint?.valid || 0 },
                  { name: "risky", value: ws?.lastPoint?.risky || 0 },
                  { name: "invalid", value: ws?.lastPoint?.invalid || 0 },
                ]}
              >
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

      {/* RECENT EVENTS */}
      <Card className="p-0 overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="text-sm font-semibold">Recent Actions</h3>
          <div className="text-xs text-gray-500">Live Feed (WebSocket)</div>
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
                <td colSpan={5} className="p-6 text-center text-gray-500">
                  No recent events
                </td>
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
