"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import UsageChart from "@/components/Dashboard/UsageChart";
import DeliverabilityChart from "@/components/Dashboard/DeliverabilityChart";
import CreditsCard from "@/components/Dashboard/CreditsCard";

export default function AdminHomePage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadStats = async () => {
    try {
      const res = await axios.get("/admin/stats");
      setStats(res.data);
    } catch (e) {
      console.error("Failed to load admin stats", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  if (loading) {
    return (
      <div className="p-10 flex justify-center">
        <Loader />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      <h1 className="text-3xl font-semibold">Admin Dashboard</h1>

      {/* Top cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <CreditsCard credits={stats.total_credits || 0} />
        <Card className="p-6">
          <p className="text-sm text-gray-500">Total Users</p>
          <p className="text-3xl font-bold mt-2">{stats.users}</p>
        </Card>
        <Card className="p-6">
          <p className="text-sm text-gray-500">Active Teams</p>
          <p className="text-3xl font-bold mt-2">{stats.teams}</p>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <UsageChart data={stats.last_7_days} />
        <DeliverabilityChart value={stats.deliverability || 0} />
      </div>

      {/* System summary */}
      <Card className="p-6">
        <h2 className="text-xl font-semibold mb-4">System Health</h2>
        <p className="text-gray-600">Jobs Running: {stats.jobs_running}</p>
        <p className="text-gray-600">Queue Size: {stats.queue_size}</p>
        <p className="text-gray-600">Webhooks Pending: {stats.webhooks_pending}</p>
      </Card>
    </div>
  );
}
