"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

import CreditsCard from "@/components/Dashboard/CreditsCard";
import UsageChart from "@/components/Dashboard/UsageChart";
import DeliverabilityChart from "@/components/Dashboard/DeliverabilityChart";

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);

  const [credits, setCredits] = useState<number>(0);
  const [usage, setUsage] = useState<any[]>([]);
  const [deliverability, setDeliverability] = useState<number>(0);
  const [recent, setRecent] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  // ------------------------------------------------
  // FETCH DASHBOARD: credits, usage, deliverability
  // ------------------------------------------------
  const loadDashboard = async () => {
    try {
      const [creditsRes, usageRes, deliverRes, recentRes] = await Promise.all([
        axios.get("/dashboard/credits"),
        axios.get("/dashboard/usage"),
        axios.get("/dashboard/deliverability"),
        axios.get("/dashboard/recent"),
      ]);

      setCredits(creditsRes.data.credits_remaining || 0);
      setUsage(usageRes.data.usage || []);
      setDeliverability(deliverRes.data.score || 0);
      setRecent(recentRes.data.items || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  };

  // Load once
  useEffect(() => {
    loadDashboard();
  }, []);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(loadDashboard, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Loader />
      </div>
    );

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      {/* HEADER */}
      <div>
        <h1 className="text-3xl font-semibold">Dashboard</h1>
        <p className="text-gray-500 mt-1">
          Monitor credits, usage, deliverability and recent verifications.
        </p>
      </div>

      {/* TOP CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Credits */}
        <CreditsCard credits={credits} />

        {/* Deliverability */}
        <DeliverabilityChart value={deliverability} />

        {/* Usage */}
        <UsageChart data={usage} />
      </div>

      {/* RECENT TABLE */}
      <Card className="p-0 overflow-hidden">
        <h2 className="text-xl font-semibold p-6 pb-2">Recent Verifications</h2>

        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-100 border-b">
            <tr>
              <th className="p-3 text-left">Email</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-left">Risk Score</th>
              <th className="p-3 text-left">Time</th>
            </tr>
          </thead>

          <tbody>
            {recent.length === 0 && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-gray-500">
                  No recent verifications
                </td>
              </tr>
            )}

            {recent.map((item: any, idx: number) => (
              <tr key={idx} className="border-b hover:bg-gray-50">
                <td className="p-3">{item.email}</td>
                <td
                  className={`p-3 font-medium ${
                    item.status === "valid"
                      ? "text-green-600"
                      : item.status === "invalid"
                      ? "text-red-600"
                      : item.status === "risky"
                      ? "text-yellow-600"
                      : "text-gray-600"
                  }`}
                >
                  {item.status}
                </td>
                <td className="p-3">{item.risk_score}</td>
                <td className="p-3 text-gray-500">
                  {new Date(item.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

"use client";

import CreditsWidget from "@/components/DashboardWidgets/CreditsWidget";
import LastVerificationWidget from "@/components/DashboardWidgets/LastVerificationWidget";
import DeliverabilityDonut from "@/components/DashboardWidgets/DeliverabilityDonut";
import BulkMiniWidget from "@/components/DashboardWidgets/BulkMiniWidget";
import ActivityFeed from "@/components/DashboardWidgets/ActivityFeed";
import useAuth from "@/hooks/useAuth";

export default function DashboardPage() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-8">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* GRID LAYOUT */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <CreditsWidget userId={user.id} />
        <LastVerificationWidget userId={user.id} />
        <DeliverabilityDonut userId={user.id} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <BulkMiniWidget userId={user.id} />
        <ActivityFeed userId={user.id} />
      </div>
    </div>
  );
}
