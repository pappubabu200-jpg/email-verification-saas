"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Loader from "@/components/ui/Loader";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function DMDiscoveryLivePage() {
  const { jobId } = useParams();
  const router = useRouter();

  const [status, setStatus] = useState("starting");
  const [progress, setProgress] = useState(0);
  const [found, setFound] = useState<any[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);

  // -----------------------------
  // CONNECT TO WS
  // -----------------------------
  useEffect(() => {
    if (!jobId) return;

    const ws = new WebSocket(
      `${process.env.NEXT_PUBLIC_WS_URL}/ws/dm-discovery/${jobId}`
    );

    ws.onopen = () => {
      console.log("WS connected");
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      // ---- PERSON FOUND ----
      if (msg.event === "person_found") {
        setFound((prev) => [...prev, msg.person]);
        setLogs((prev) => [
          `[FOUND] ${msg.person.name}, ${msg.person.title}`,
          ...prev,
        ]);
      }

      // ---- EMAIL PATTERN GUESS ----
      if (msg.event === "email_guess") {
        setLogs((prev) => [
          `[GUESS] ${msg.candidate} for ${msg.person}`,
          ...prev,
        ]);
      }

      // ---- EMAIL VERIFIED ----
      if (msg.event === "email_verified") {
        setLogs((prev) => [
          `[VERIFIED] ${msg.email} → ${msg.status}`,
          ...prev,
        ]);
      }

      // ---- ENRICHED DETAIL ----
      if (msg.event === "enriched") {
        setLogs((prev) => [
          `[ENRICHED] ${msg.email} enriched (Apollo + PDL)`,
          ...prev,
        ]);

        // update final list if record exists
        setFound((prev) =>
          prev.map((p) =>
            p.email === msg.email
              ? { ...p, enrichment: msg.enrichment }
              : p
          )
        );
      }

      // ---- PROGRESS ----
      if (msg.event === "progress") {
        setProgress(msg.progress || 0);
      }

      // ---- COMPLETED ----
      if (msg.event === "completed") {
        setCompleted(true);
        setStatus("completed");
        setLogs((prev) => ["✔ Discovery completed", ...prev]);
        ws.close();
      }

      // ---- FAILED ----
      if (msg.event === "failed") {
        setStatus("failed");
        setError(msg.error || "Discovery failed");
        setLogs((prev) => ["❌ FAILED: " + msg.error, ...prev]);
        ws.close();
      }
    };

    ws.onerror = () => {
      console.error("WS error");
    };

    ws.onclose = () => {
      console.log("WS closed");
    };

    return () => ws.close();
  }, [jobId]);

  // -----------------------------
  // UI RENDER
  // -----------------------------
  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Discovery Progress</h1>
          <p className="text-sm text-gray-500">
            Job ID: <code>{jobId}</code>
          </p>
        </div>

        {completed && (
          <Button
            variant="primary"
            onClick={() => router.push("/decision-maker/results/" + jobId)}
          >
            View Results
          </Button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {/* PROGRESS CARD */}
      <Card className="p-6 space-y-4">
        <p className="text-sm text-gray-700">
          Status:{" "}
          <span
            className={
              status === "completed"
                ? "text-green-600 font-semibold"
                : status === "failed"
                ? "text-red-600 font-semibold"
                : "text-blue-600 font-semibold"
            }
          >
            {status.toUpperCase()}
          </span>
        </p>

        {/* Progress bar */}
        <div className="w-full bg-gray-200 h-3 rounded-full">
          <div
            className="bg-blue-600 h-full rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        <p className="text-sm text-gray-500">{progress}% completed</p>
      </Card>

      {/* FOUND PEOPLE */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">People Found ({found.length})</h2>
        <div className="space-y-3">
          {found.map((p, idx) => (
            <div key={idx} className="border-b pb-2">
              <p className="font-bold">{p.name}</p>
              <p className="text-gray-600 text-sm">
                {p.title} @ {p.company}
              </p>
              {p.email && (
                <p className="text-sm mt-1">
                  Email: <b>{p.email}</b>
                </p>
              )}
              {p.enrichment && (
                <p className="text-xs text-green-600">
                  ✓ Enriched (Apollo + PDL)
                </p>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* LOGS */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Live Logs</h2>
        <div className="h-64 overflow-y-auto text-sm bg-gray-50 p-4 rounded">
          {logs.map((l, i) => (
            <div key={i} className="mb-1">
              {l}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
