"use client";

import { useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function BulkUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [estimated, setEstimated] = useState<number | null>(null);

  const handleFile = (e: any) => {
    setFile(e.target.files[0]);
    setEstimated(null);
    setError(null);
  };

  const uploadCsv = async () => {
    if (!file) {
      setError("Please upload a CSV file.");
      return;
    }

    setError(null);
    setSuccess(null);
    setUploading(true);

    try {
      // Step 1: Upload file → backend returns upload_id
      const formData = new FormData();
      formData.append("file", file);

      const uploadResp = await axios.post("/bulk_jobs/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const { upload_id, email_count } = uploadResp.data;

      setEstimated(email_count);

      // Step 2: Create the bulk job
      const jobRes = await axios.post("/bulk_jobs/create", {
        upload_id,
      });

      setSuccess("Bulk job created!");
      const jobId = jobRes.data.job_id;

      // Step 3: Redirect to job detail page
      window.location.href = `/bulk/${jobId}`;
    } catch (err: any) {
      const msg =
        err.response?.data?.detail || err.response?.data?.message || "Upload failed";
      setError(String(msg));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-8">
      <h1 className="text-3xl font-semibold">Bulk Email Verification</h1>
      <p className="text-gray-600">
        Upload a CSV file containing email addresses. We'll verify them in parallel with
        the fastest SMTP engine (with domain backoff & concurrency throttling).
      </p>

      <Card>
        <div className="space-y-6">
          <div>
            <label className="text-sm font-medium">Upload CSV File</label>
            <input
              type="file"
              accept=".csv"
              onChange={handleFile}
              className="block w-full mt-2 border border-gray-300 rounded p-2"
            />
          </div>

          {estimated && (
            <div className="bg-blue-50 p-3 rounded text-blue-700 text-sm">
              Estimated emails: <b>{estimated}</b>
            </div>
          )}

          {error && <ErrorBanner message={error} />}
          {success && <SuccessBanner message={success} />}

          <Button
            className="w-full"
            onClick={uploadCsv}
            disabled={uploading}
            variant="primary"
          >
            {uploading ? (
              <div className="flex items-center gap-2">
                <Loader /> Uploading...
              </div>
            ) : (
              "Upload & Start Verification"
            )}
          </Button>
        </div>
      </Card>
    </div>
  );
}

"use client";

import { useState, useEffect } from "react";
import axios from "@/lib/axios";
import CsvUploader from "@/components/Bulk/CsvUploader";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Link from "next/link";

export default function BulkFinderPage() {
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [jobName, setJobName] = useState<string>("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);

  // optional: load recent jobs
  useEffect(() => {
    fetchJobs();
  }, []);

  async function fetchJobs() {
    setLoadingJobs(true);
    try {
      const res = await axios.get("/bulk/jobs");
      setJobs(res.data || []);
    } catch (err: any) {
      // ignore; show nothing
      console.error("Failed to load bulk jobs", err);
    } finally {
      setLoadingJobs(false);
    }
  }

  const handleUploaded = (id: string) => {
    setUploadId(id);
    setError(null);
  };

  const handleCreateJob = async () => {
    setError(null);
    if (!uploadId) return setError("Please upload a CSV first.");
    if (!jobName || jobName.trim().length < 3) {
      return setError("Give the job a descriptive name (min 3 chars).");
    }

    setCreating(true);
    try {
      const payload = { upload_id: uploadId, name: jobName.trim() };
      const res = await axios.post("/bulk/create", payload);
      // push new job to list
      setJobs((s) => [res.data, ...(s || [])]);
      setUploadId(null);
      setJobName("");
      alert("Bulk job created — go to job details to monitor progress.");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create bulk job");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen p-8 bg-gray-50">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Bulk Decision Maker Finder</h1>
          <p className="text-sm text-gray-500">Upload domains or company list to find decision makers</p>
        </div>

        {error && <ErrorBanner message={error} />}

        <Card className="p-6">
          <h2 className="text-lg font-medium mb-3">1. Upload CSV</h2>
          <p className="text-sm text-gray-500 mb-4">
            CSV format: one column with domain or company per row or email list. Example: <code>example.com</code>
          </p>

          <CsvUploader onUploaded={handleUploaded} accept=".csv" />

          {uploadId && (
            <div className="mt-4">
              <label className="block text-sm font-medium text-gray-700">Job Name</label>
              <input
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
                placeholder="e.g. Q4 Prospecting - Acme domains"
                className="mt-2 p-2 border rounded w-full"
              />
              <div className="mt-3 flex gap-3">
                <Button onClick={handleCreateJob} disabled={creating}>
                  {creating ? <div className="flex items-center gap-2"><Loader /> Creating...</div> : "Create Bulk Job"}
                </Button>
                <Button onClick={() => { setUploadId(null); setJobName(""); }} variant="secondary">
                  Cancel
                </Button>
              </div>
              <p className="text-xs text-gray-400 mt-2">Upload id: <code>{uploadId}</code></p>
            </div>
          )}
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Recent Bulk Jobs</h3>
            <div>
              <Button onClick={fetchJobs} variant="ghost" disabled={loadingJobs}>
                {loadingJobs ? "Refreshing..." : "Refresh"}
              </Button>
            </div>
          </div>

          {!jobs.length && <p className="text-sm text-gray-500">No bulk jobs yet.</p>}

          <div className="space-y-3">
            {jobs.map((j: any) => (
              <div key={j.id} className="flex items-center justify-between border rounded p-3">
                <div>
                  <div className="font-medium">{j.name || `Job #${j.id}`}</div>
                  <div className="text-sm text-gray-500">Status: <span className="font-medium">{j.status}</span></div>
                  <div className="text-xs text-gray-400">Created: {new Date(j.created_at).toLocaleString()}</div>
                </div>
                <div className="flex items-center gap-3">
                  <Link href={`/bulk/${j.id}`} className="text-blue-600 hover:underline">Open</Link>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
