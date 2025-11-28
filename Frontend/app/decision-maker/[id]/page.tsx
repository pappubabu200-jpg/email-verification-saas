"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";

import DMEnrichButton from "@/components/DecisionMaker/DMEnrichButton";
import { useDMEnrichmentWS } from "@/hooks/useDMEnrichmentWS";

export default function DecisionMakerDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const dmId = String(id);

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 🔥 Real-time Enrichment WebSocket
  const { event } = useDMEnrichmentWS(dmId);

  // -------------------------------------
  // FETCH PROFILE
  // -------------------------------------
  const fetchProfile = async () => {
    try {
      const res = await axios.get(`/decision-maker/${dmId}`);
      setData(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load profile");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, [dmId]);

  // Refresh DM detail when enrichment completes
  useEffect(() => {
    if (!event) return;

    if (event.event === "enrich_completed") {
      fetchProfile();
    }
  }, [event]);

  // -------------------------------------
  // VERIFY EMAIL
  // -------------------------------------
  const handleVerifyEmail = async () => {
    if (!data?.profile?.email) return;

    setVerifying(true);
    try {
      const res = await axios.get("/verification/single", {
        params: { email: data.profile.email },
      });
      alert("Verification Result: " + res.data.status);
    } catch (err) {
      alert("Verification failed.");
    } finally {
      setVerifying(false);
    }
  };

  // -------------------------------------
  // LOADING / ERROR
  // -------------------------------------
  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Loader />
      </div>
    );

  if (error) return <ErrorBanner message={error} />;
  if (!data) return null;

  const person = data.profile || {};
  const company = data.company || {};
  const enrichment = data.enrichment || {};

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-8">

      {/* HEADER */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">{person.name}</h1>
          <p className="text-gray-600">{person.title}</p>
          <p className="text-gray-500">{company.name}</p>

          {data.confidence && (
            <p className="text-xs text-gray-500 mt-1">
              Confidence Score: <b>{data.confidence}%</b>
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={() => router.push("/decision-maker")}>Back</Button>
          <DMEnrichButton dmId={dmId} />
          <Button onClick={handleVerifyEmail} disabled={verifying} variant="secondary">
            {verifying ? "Verifying…" : "Verify Email"}
          </Button>
        </div>
      </div>

      {/* REAL-TIME ENRICHMENT STATUS */}
      {event && (
        <div className="p-3 rounded bg-blue-50 border text-blue-700 text-sm">
          {event.event === "enrich_started" && "Enrichment started…"}
          {event.event === "progress" && `Step: ${event.step || "Processing…"}`}
          {event.event === "enrich_completed" && "Enrichment completed!"}
          {event.event === "failed" && (
            <span className="text-red-600">Error: {event.error}</span>
          )}
        </div>
      )}

      {/* CONTACT CARD */}
      <Card className="p-6 space-y-4">
        <div className="flex items-center gap-6">
          <div className="rounded-full h-20 w-20 bg-gray-200 flex items-center justify-center text-3xl">
            {person.name?.charAt(0)}
          </div>

          <div>
            <h2 className="text-xl font-semibold">{person.name}</h2>
            <p className="text-gray-600">{person.title}</p>
            <p className="text-gray-500">{company.name}</p>
          </div>
        </div>

        {/* CONTACT INFO GRID */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
          <div>
            <p className="text-xs text-gray-500">Email</p>
            <p className="font-medium">{person.email || "Not available"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Phone</p>
            <p className="font-medium">{person.phone || "Not available"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Seniority</p>
            <p className="font-medium">{person.seniority || "-"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Department</p>
            <p className="font-medium">{person.department || "-"}</p>
          </div>
        </div>

        {/* SOCIAL LINKS */}
        <div className="flex gap-4 mt-4">
          {person.linkedin && (
            <a href={person.linkedin} target="_blank" className="text-blue-600 hover:underline">
              LinkedIn
            </a>
          )}
          {person.twitter && (
            <a href={person.twitter} target="_blank" className="text-blue-600 hover:underline">
              Twitter
            </a>
          )}
          {person.github && (
            <a href={person.github} target="_blank" className="text-blue-600 hover:underline">
              GitHub
            </a>
          )}
        </div>
      </Card>

      {/* COMPANY CARD */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Company Info</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <p><b>Name:</b> {company.name || "-"}</p>
          <p><b>Domain:</b> {company.domain || "-"}</p>
          <p><b>Industry:</b> {company.industry || "-"}</p>
          <p><b>Employees:</b> {company.size || "-"}</p>
          <p><b>Location:</b> {company.location || "-"}</p>
        </div>
      </Card>

      {/* JOB HISTORY */}
      {person.experience?.length > 0 && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">Job History</h2>
          <div className="space-y-3">
            {person.experience.map((job: any, idx: number) => (
              <div key={idx} className="border-b pb-3">
                <p className="font-semibold">{job.title}</p>
                <p className="text-gray-600">{job.company}</p>
                <p className="text-xs text-gray-500">
                  {job.start} - {job.end ?? "Present"}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ENRICHMENT JSON */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Enrichment Data</h2>
        <pre className="text-xs p-4 bg-gray-100 rounded overflow-auto">
          {JSON.stringify(enrichment, null, 2)}
        </pre>
      </Card>

    </div>
  );
}
