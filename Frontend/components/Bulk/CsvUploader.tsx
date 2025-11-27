"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";

type Props = {
  onUploaded: (uploadId: string) => void;
  accept?: string;
};

export default function CsvUploader({ onUploaded, accept = ".csv" }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewRows, setPreviewRows] = useState<string[]>([]);

  const handleFile = (f: File | null) => {
    setError(null);
    setPreviewRows([]);
    if (!f) {
      setFile(null);
      return;
    }
    if (!f.name.toLowerCase().endsWith(".csv")) {
      setError("Please upload a CSV file.");
      return;
    }
    setFile(f);
    // quick preview (first 10 lines)
    const reader = new FileReader();
    reader.onload = (ev: any) => {
      const txt: string = String(ev.target.result || "");
      const rows = txt.split(/\r?\n/).slice(0, 10).map((r) => r.trim()).filter(Boolean);
      setPreviewRows(rows);
    };
    reader.readAsText(f.slice(0, 64 * 1024)); // read first 64KB
  };

  const handleUpload = async () => {
    if (!file) return setError("Choose a CSV file first.");
    setUploading(true);
    setProgress(0);
    setError(null);

    try {
      const form = new FormData();
      form.append("file", file);

      const res = await axios.post("/bulk/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (ev: any) => {
          if (ev.total) {
            setProgress(Math.round((ev.loaded / ev.total) * 100));
          }
        },
        timeout: 120000, // large upload timeout
      });

      const uploadId = res.data?.upload_id || res.data?.id;
      if (!uploadId) throw new Error("Invalid upload response");
      onUploaded(uploadId);
      setFile(null);
      setPreviewRows([]);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || "Upload failed");
    } finally {
      setUploading(false);
      setProgress(null);
    }
  };

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">CSV file</label>

      <div className="mt-2 flex gap-3 items-center">
        <input
          type="file"
          accept={accept}
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          className="block"
        />
        <div>
          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading ? <div className="flex items-center gap-2"><Loader /> Uploading...</div> : "Upload CSV"}
          </Button>
        </div>
      </div>

      {progress !== null && (
        <div className="mt-2 text-sm text-gray-600">Progress: {progress}%</div>
      )}

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      {previewRows.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-gray-500 mb-2">Preview (first {previewRows.length} rows):</div>
          <div className="bg-white border rounded p-3 text-sm">
            {previewRows.map((r, idx) => (
              <div key={idx} className="truncate">{r}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
      }
