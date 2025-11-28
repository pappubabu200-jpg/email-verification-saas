"use client";

import { useEffect, useState, useMemo } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";

import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

export default function DMAnalyticsDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [analytics, setAnalytics] = useState<any>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get("/admin/dm/analytics");
      setAnalytics(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000); // auto-refresh
    return () => clearInterval(interval);
  }, []);

  if (loading) return (
    <div className="p-10">
      <Loader />
    </div>
  );

  if (error) return <ErrorBanner message={error} />;

  const COLORS = ["#3b82f6", "#34d399", "#f59e0b", "#ef4444", "#6366f1", "#10b981"];

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-10">
      {/* HEADER */}
      <div>
        <h1 className="text-3xl font-semibold">Decision Maker Analytics</h1>
        <p className="text-gray-600 mt-1">
          Insights from enriched executive data, updated continuously.
        </p>
      </div>

      {/* TOP STATS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-6">
          <div className="text-sm text-gray-500">Total Profiles</div>
          <div className="text-3xl font-bold mt-2">
            {analytics.total.toLocaleString()}
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-sm text-gray-500">Verified Email %</div>
          <div className="text-3xl font-bold mt-2">
            {analytics.verified_pct}%
          </div>
        </Card>

        <Card className="p-6">
          <div className="text-sm text-gray-500">Top Department</div>
          <div className="text-xl font-bold mt-2">
            {analytics.by_department[0]?.department || "—"}
          </div>
        </Card>
      </div>

      {/* GRIDS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* 1️⃣ BY DEPARTMENT (BAR CHART) */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">By Department</h2>

          <div className="h-80">
            <ResponsiveContainer>
              <BarChart data={analytics.by_department}>
                <XAxis dataKey="department" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count">
                  {analytics.by_department.map((_: any, i: number) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 2️⃣ BY SENIORITY (PIE CHART) */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">By Seniority</h2>

          <div className="h-80">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={analytics.by_seniority}
                  dataKey="count"
                  nameKey="seniority"
                  outerRadius={120}
                  label
                >
                  {analytics.by_seniority.map((_: any, i: number) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 3️⃣ BY TITLE (BAR VERTICAL) */}
        <Card className="p-6 col-span-2">
          <h2 className="text-lg font-semibold mb-4">Top Titles</h2>

          <div className="h-80">
            <ResponsiveContainer>
              <BarChart data={analytics.by_title}>
                <XAxis dataKey="title" hide />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* 4️⃣ LOCATION REPRESENTATION */}
        <Card className="p-6 col-span-2">
          <h2 className="text-lg font-semibold mb-4">By Location</h2>

          <div className="h-80">
            <ResponsiveContainer>
              <LineChart data={analytics.by_location}>
                <XAxis dataKey="location" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#3b82f6" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

      </div>
    </div>
  );
}
