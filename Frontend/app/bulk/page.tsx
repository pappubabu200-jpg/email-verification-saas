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
