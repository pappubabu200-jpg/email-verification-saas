"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function BulkJobDetailPage() {
  const { jobId } = useParams();
  const [job, setJob] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------
  // Fetch initial job snapshot
  // ---------------------------------------------------------
  const fetchJob = async () => {
    try {
      const res = await axios.get(`/bulk/${jobId}`);
      setJob(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load job details");
    } finally {
      setLoading(false);
    }
  };

  // ---------------------------------------------------------
  // Initial Load
  // ---------------------------------------------------------
  useEffect(() => {
    fetchJob();
  }, [jobId]);

  // ---------------------------------------------------------
  // WebSocket LIVE UPDATES
  // ---------------------------------------------------------
  useEffect(() => {
    if (!jobId) return;

    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL}/ws/bulk/${jobId}`;
    console.log("🔌 Connecting to Bulk WS:", wsUrl);

    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);
      console.log("📡 WS:", update);

      // Live progress
      if (update.event === "progress") {
        setJob((prev: any) => ({
          ...prev,
          processed: update.processed,
          total: update.total,
          stats: update.stats,
          status: "running",
        }));
      }

      // Finished
      if (update.event === "completed") {
        setJob((prev: any) => ({
          ...prev,
          status: "completed",
          processed: update.total,
          total: update.total,
          stats: update.stats,
        }));
        ws.close();
      }

      // Failed
      if (update.event === "failed") {
        setJob((prev: any) => ({
          ...prev,
          status: "failed",
        }));
        ws.close();
      }
    };

    ws.onerror = () => console.error("❌ WebSocket error");
    ws.onclose = () => console.log("🔌 Bulk WebSocket closed");

    return () => ws.close();
  }, [jobId]);

  // ---------------------------------------------------------
  // Render UI
  // ---------------------------------------------------------
  if (loading)
    return (
      <div className="flex justify-center p-20">
        <Loader />
      </div>
    );

  if (error) return <ErrorBanner message={error} />;

  if (!job) return <p className="p-8 text-red-600">Job not found</p>;

  const progress =
    job.total && job.processed ? Math.round((job.processed / job.total) * 100) : 0;

  const stats = job.stats || {
    valid: 0,
    risky: 0,
    invalid: 0,
    unknown: 0,
  };

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-8">
      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{job.name || "Bulk Job"}</h1>
          <p className="text-sm text-gray-500">
            Job ID: <code>{jobId}</code>
          </p>
        </div>

        {job.status === "completed" && (
          <Button
            onClick={() => {
              window.location.href = `/bulk/${jobId}/download`;
            }}
            variant="primary"
          >
            Download CSV
          </Button>
        )}
      </div>

      {/* STATUS CARD */}
      <Card className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <p className="text-lg font-semibold">
            Status: {job.status?.toUpperCase()}
          </p>
          <p className="text-sm text-gray-500">
            {job.processed}/{job.total} processed
          </p>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-gray-200 h-3 rounded">
          <div
            className="bg-blue-600 h-full rounded transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
          <div className="p-3 border rounded bg-white">
            <p className="text-xs text-gray-600">Valid</p>
            <p className="font-bold text-green-600">{stats.valid}</p>
          </div>

          <div className="p-3 border rounded bg-white">
            <p className="text-xs text-gray-600">Risky</p>
            <p className="font-bold text-yellow-600">{stats.risky}</p>
          </div>

          <div className="p-3 border rounded bg-white">
            <p className="text-xs text-gray-600">Invalid</p>
            <p className="font-bold text-red-600">{stats.invalid}</p>
          </div>

          <div className="p-3 border rounded bg-white">
            <p className="text-xs text-gray-600">Unknown</p>
            <p className="font-bold text-blue-600">{stats.unknown}</p>
          </div>
        </div>
      </Card>

      {/* RESULTS TABLE */}
      {job.results && job.results.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm border-collapse">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="p-3 text-left">Email</th>
                <th className="p-3 text-left">Status</th>
                <th className="p-3 text-left">Score</th>
                <th className="p-3 text-left">Reason</th>
              </tr>
            </thead>
            <tbody>
              {job.results.map((row: any, idx: number) => (
                <tr key={idx} className="border-b hover:bg-gray-50">
                  <td className="p-3">{row.email}</td>
                  <td className="p-3 capitalize">{row.status}</td>
                  <td className="p-3">{row.score}</td>
                  <td className="p-3 text-gray-500">{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
