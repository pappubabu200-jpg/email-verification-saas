"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function DMResultsPage() {
  const { jobId } = useParams();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [results, setResults] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [error, setError] = useState<string | null>(null);

  // --------------------------------------------------
  // LOAD RESULTS FROM BACKEND
  // --------------------------------------------------
  const loadResults = async () => {
    try {
      const res = await axios.get(`/decision-maker/results/${jobId}`);
      setResults(res.data.items || []);
      setSummary(res.data.summary || {});
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load results");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (jobId) loadResults();
  }, [jobId]);

  if (loading)
    return (
      <div className="flex justify-center p-20">
        <Loader />
      </div>
    );

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Discovery Results</h1>
          <p className="text-sm text-gray-500">
            Job ID: <code>{jobId}</code>
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() =>
            window.open(`/decision-maker/results/${jobId}/export`)
          }
        >
          Export CSV
        </Button>
      </div>

      {/* SUMMARY */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Summary</h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 bg-white border rounded">
            <p className="text-xs text-gray-500">Total Found</p>
            <p className="text-2xl font-bold">{summary.total || 0}</p>
          </div>

          <div className="p-4 bg-white border rounded">
            <p className="text-xs text-gray-500">Verified Emails</p>
            <p className="text-2xl font-bold text-green-600">
              {summary.verified || 0}
            </p>
          </div>

          <div className="p-4 bg-white border rounded">
            <p className="text-xs text-gray-500">Enriched</p>
            <p className="text-2xl font-bold text-blue-600">
              {summary.enriched || 0}
            </p>
          </div>

          <div className="p-4 bg-white border rounded">
            <p className="text-xs text-gray-500">Domains</p>
            <p className="text-2xl font-bold">{summary.domains || 0}</p>
          </div>
        </div>
      </Card>

      {/* TABLE */}
      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="p-3 text-left">Name</th>
              <th className="p-3 text-left">Title</th>
              <th className="p-3 text-left">Company</th>
              <th className="p-3 text-left">Email</th>
              <th className="p-3 text-left">Status</th>
              <th className="p-3 text-left">Enriched</th>
              <th className="p-3 text-left"></th>
            </tr>
          </thead>

          <tbody>
            {results.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center p-6 text-gray-500">
                  No results.
                </td>
              </tr>
            )}

            {results.map((r, idx) => (
              <tr key={idx} className="border-b hover:bg-gray-50">
                <td className="p-3 font-medium">{r.name}</td>
                <td className="p-3">{r.title}</td>
                <td className="p-3">{r.company}</td>
                <td className="p-3">{r.email || "--"}</td>

                {/* Status */}
                <td className="p-3">
                  <span
                    className={`px-2 py-1 rounded text-xs ${
                      r.status === "valid"
                        ? "bg-green-100 text-green-700"
                        : r.status === "invalid"
                        ? "bg-red-100 text-red-600"
                        : "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {r.status || "unknown"}
                  </span>
                </td>

                {/* Enriched */}
                <td className="p-3">
                  {r.enriched ? (
                    <span className="text-green-600 font-semibold">Yes</span>
                  ) : (
                    <span className="text-gray-500">No</span>
                  )}
                </td>

                {/* Details Button */}
                <td className="p-3 text-right">
                  <Button
                    variant="secondary"
                    onClick={() => router.push(`/decision-maker/${r.id}`)}
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
