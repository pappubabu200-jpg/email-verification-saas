// Frontend/app/decision-maker/bulk/page.tsx
"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Loader from "@/components/ui/Loader";
import { useRouter } from "next/navigation";

export default function DMBulkUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  const submit = async () => {
    setError(null);
    if (!file && !text) {
      setError("Upload CSV of domains or paste domain list");
      return;
    }
    setLoading(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      if (text) form.append("domains_text", text);
      // optional user_id
      // form.append("user_id","123")

      const res = await axios.post("/dm/bulk/create", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const jobId = res.data.job_id;
      router.push(`/decision-maker/bulk/${jobId}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-8">
      <h1 className="text-2xl font-semibold mb-4">Decision Maker Bulk Finder</h1>

      <div className="mb-6">
        <label className="block text-sm font-medium">Upload CSV (one domain per row)</label>
        <input type="file" accept=".csv" onChange={(e:any)=>setFile(e.target.files?.[0]||null)} className="mt-2" />
      </div>

      <div className="mb-6">
        <label className="block text-sm font-medium">Or paste domains (newline separated)</label>
        <textarea value={text} onChange={(e)=>setText(e.target.value)} rows={6} className="w-full border p-2 rounded mt-2" />
      </div>

      {error && <div className="text-red-600 mb-4">{error}</div>}

      <div>
        <Button onClick={submit} disabled={loading}>
          {loading ? <><Loader /> Submitting...</> : "Start Discovery"}
        </Button>
      </div>
    </div>
  );
}
