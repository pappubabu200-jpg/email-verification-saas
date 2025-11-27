"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function BulkJobDetailPage() {
  const { jobId } = useParams();

  const [job, setJob] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ------------------------------
  // Fetch job status
  // ------------------------------
  const fetchJob = async () => {
    try {
      const res = await axios.get(`/bulk_jobs/${jobId}`);
      setJob(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load job");
      setPolling(false);
    } finally {
      setLoading(false);
    }
  };

  // Poll every 3 seconds until completed
  useEffect(() => {
    fetchJob();
    if (polling) {
      const timer = setInterval(fetchJob, 3000);
      return () => clearInterval(timer);
    }
  }, [polling]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader />
      </div>
    );
  }

  if (!job) {
    return <ErrorBanner message="Job not found." />;
  }

  const {
    status,
    total_emails,
    processed,
    failed,
    started_at,
    finished_at,
    download_csv,
    download_json
  } = job;

  const progress = total_emails
    ? Math.round((processed / total_emails) * 100)
    : 0;

  // Stop polling when job finished
  if (status === "completed" || status === "failed") {
    if (polling) setPolling(false);
  }

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      <h1 className="text-3xl font-semibold">Bulk Job #{jobId}</h1>
      <p className="text-gray-600">Track progress of your uploaded CSV file.</p>

      {/* Status Card */}
      <Card>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">Status</p>
            <span
              className={`px-3 py-1 rounded text-sm font-medium ${
                status === "completed"
                  ? "bg-green-100 text-green-700"
                  : status === "running"
                  ? "bg-blue-100 text-blue-700"
                  : status === "failed"
                  ? "bg-red-100 text-red-700"
                  : "bg-gray-100 text-gray-700"
              }`}
            >
              {status.toUpperCase()}
            </span>
          </div>

          <div>
            <p className="text-sm text-gray-500">Progress</p>
            <p className="text-xl font-bold">{progress}%</p>
          </div>

          <div>
            <p className="text-sm text-gray-500">Processed</p>
            <p className="text-xl font-bold">
              {processed} / {total_emails}
            </p>
          </div>

          <div>
            <p className="text-sm text-gray-500">Failed</p>
            <p className="text-xl font-bold text-red-600">{failed}</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-6 w-full bg-gray-200 h-3 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-600 transition-all"
            style={{ width: `${progress}%` }}
          ></div>
        </div>

        <div className="mt-4 text-sm text-gray-600">
          Started: {started_at ? new Date(started_at).toLocaleString() : "--"}
          <br />
          Finished: {finished_at ? new Date(finished_at).toLocaleString() : "--"}
        </div>
      </Card>

      {/* Downloads */}
      {status === "completed" && (
        <Card>
          <h2 className="text-lg font-semibold mb-4">Download Results</h2>

          <div className="flex gap-4">
            {download_csv && (
              <Button
                variant="primary"
                onClick={() => window.open(download_csv)}
              >
                Download CSV
              </Button>
            )}

            {download_json && (
              <Button
                variant="secondary"
                onClick={() => window.open(download_json)}
              >
                Download JSON
              </Button>
            )}
          </div>
        </Card>
      )}

      {/* Error Section */}
      {status === "failed" && (
        <Card>
          <h2 className="text-lg font-semibold mb-2 text-red-600">Job Failed</h2>
          <p className="text-gray-600">
            Something went wrong while processing the job. Please retry or upload a
            smaller file.
          </p>
        </Card>
      )}
    </div>
  );
      }

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
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch job details
  const fetchJob = async () => {
    try {
      const res = await axios.get(`/bulk/${jobId}`);
      setJob(res.data);

      // Stop polling if completed or failed
      if (["completed", "failed", "error"].includes(res.data.status)) {
        setPolling(false);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load job details");
    } finally {
      setLoading(false);
    }
  };

  // Poll every 2.5 seconds
  useEffect(() => {
    fetchJob();
    if (!polling) return;

    const interval = setInterval(fetchJob, 2500);
    return () => clearInterval(interval);
  }, [jobId, polling]);

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

  // Stats
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
          <h1 className="text-2xl font-semibold">{job.name}</h1>
          <p className="text-sm text-gray-500">
            Job ID: <code>{job.id}</code>
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
          <p className="text-lg font-semibold">Status: {job.status.toUpperCase()}</p>
          <p className="text-sm text-gray-500">
            {job.processed}/{job.total} completed
          </p>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-gray-200 h-3 rounded">
          <div
            className="bg-blue-600 h-full rounded transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
          <div className="p-3 rounded border bg-white">
            <p className="text-xs text-gray-600">Valid</p>
            <p className="font-bold text-green-600">{stats.valid}</p>
          </div>

          <div className="p-3 rounded border bg-white">
            <p className="text-xs text-gray-600">Risky</p>
            <p className="font-bold text-yellow-600">{stats.risky}</p>
          </div>

          <div className="p-3 rounded border bg-white">
            <p className="text-xs text-gray-600">Invalid</p>
            <p className="font-bold text-red-600">{stats.invalid}</p>
          </div>

          <div className="p-3 rounded border bg-white">
            <p className="text-xs text-gray-600">Unknown</p>
            <p className="font-bold text-blue-600">{stats.unknown}</p>
          </div>
        </div>
      </Card>

      {/* RESULTS TABLE */}
      {job.results && job.results.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <table className="w-full border-collapse text-sm">
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

