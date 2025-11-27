"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Table from "@/components/ui/Table";
import Loader from "@/components/ui/Loader";

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [credits, setCredits] = useState(0);
  const [deliverability, setDeliverability] = useState(null);
  const [recent, setRecent] = useState([]);

  // Fetch Dashboard Data
  const loadData = async () => {
    try {
      const [usageRes, deliverRes, recentRes] = await Promise.all([
        axios.get("/usage/summary"),
        axios.get("/analytics/domain-health"),
        axios.get("/verification/recent"),
      ]);

      setCredits(usageRes.data.available_credits || 0);
      setDeliverability(deliverRes.data || null);
      setRecent(recentRes.data.results || []);
    } catch (err) {
      console.error("Dashboard load failed:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="h-full flex justify-center items-center">
        <Loader />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-gray-500 text-sm">Welcome back! Here's your verification overview.</p>
      </div>

      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Credits */}
        <Card>
          <h2 className="text-lg font-semibold mb-2">Available Credits</h2>
          <p className="text-3xl font-bold text-blue-600">{credits.toLocaleString()}</p>
          <Button className="mt-4 w-full" variant="primary">Buy Credits</Button>
        </Card>

        {/* Deliverability Score */}
        <Card>
          <h2 className="text-lg font-semibold mb-2">Deliverability Health</h2>
          {deliverability ? (
            <p className="text-3xl font-bold text-green-600">{deliverability.score}%</p>
          ) : (
            <p className="text-gray-500">No data yet</p>
          )}
          <Button className="mt-4 w-full" variant="secondary">View Report</Button>
        </Card>

        {/* Quick Actions */}
        <Card>
          <h2 className="text-lg font-semibold mb-2">Quick Actions</h2>
          <div className="space-y-3">
            <Button className="w-full" onClick={() => location.href = "/verification"}>Verify Single Email</Button>
            <Button className="w-full" onClick={() => location.href = "/bulk"} variant="secondary">
              Bulk Verification
            </Button>
            <Button className="w-full" onClick={() => location.href = "/api-keys"} variant="outline">
              API Keys
            </Button>
          </div>
        </Card>
      </div>

      {/* Recent Verifications */}
      <Card>
        <h2 className="text-lg font-semibold mb-4">Recent Verifications</h2>

        {recent.length === 0 ? (
          <p className="text-gray-500 text-sm">No recent verifications found.</p>
        ) : (
          <Table
            headers={["Email", "Status", "Risk", "Date"]}
            rows={recent.map((row) => [
              row.email,
              row.status,
              row.risk_score,
              new Date(row.created_at).toLocaleString(),
            ])}
          />
        )}
      </Card>
    </div>
  );
}
