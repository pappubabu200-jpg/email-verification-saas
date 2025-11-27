
"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function DecisionMakerDetailPage() {
  const { id } = useParams();
  const router = useRouter();

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // -------------------------------------
  // Fetch decision maker profile
  // -------------------------------------
  const fetchProfile = async () => {
    try {
      const res = await axios.get(`/decision-maker/${id}`);
      setData(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load profile");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) fetchProfile();
  }, [id]);

  const handleVerifyEmail = async () => {
    if (!data?.email) return;

    setVerifying(true);
    try {
      const res = await axios.get("/verification/single", {
        params: { email: data.email },
      });
      alert("Verification Result: " + res.data.status);
    } catch (err: any) {
      alert("Verification failed.");
    } finally {
      setVerifying(false);
    }
  };

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

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-8">
      {/* Top Section */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">{person.name}</h1>

        <div className="flex items-center gap-3">
          <Button onClick={() => router.push("/decision-maker")}>Back</Button>
          <Button onClick={handleVerifyEmail} disabled={verifying} variant="primary">
            {verifying ? "Verifying..." : "Verify Email"}
          </Button>
        </div>
      </div>

      {/* Contact Card */}
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

        {/* Contact Info */}
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

        {/* Social Links */}
        <div className="flex gap-4 mt-4">
          {person.linkedin && (
            <a
              href={person.linkedin}
              target="_blank"
              className="text-blue-600 hover:underline"
            >
              LinkedIn
            </a>
          )}
          {person.twitter && (
            <a
              href={person.twitter}
              target="_blank"
              className="text-blue-600 hover:underline"
            >
              Twitter
            </a>
          )}
          {person.github && (
            <a
              href={person.github}
              target="_blank"
              className="text-blue-600 hover:underline"
            >
              GitHub
            </a>
          )}
        </div>
      </Card>

      {/* Company Card */}
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

      {/* Job History */}
      {person.experience && person.experience.length > 0 && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-4">Job History</h2>

          <div className="space-y-3">
            {person.experience.map((job: any, idx: number) => (
              <div key={idx} className="border-b pb-3">
                <p className="font-semibold">{job.title}</p>
                <p className="text-gray-600">{job.company}</p>
                <p className="text-xs text-gray-500">{job.start} - {job.end ?? "Present"}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import axios from "@/lib/axios";
import DMDetailTabs from "@/components/DecisionMaker/DMDetailTabs";

export default function DMDetailPage() {
  const { id } = useParams();
  const [dm, setDm] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await axios.get(`/decision-maker/${id}`);
        setDm(res.data);
      } catch (err) {
        console.error("Failed to load decision-maker details", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  if (loading) return <p className="p-8">Loading...</p>;
  if (!dm) return <p className="p-8 text-red-600">Not found</p>;

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-3xl font-semibold">{dm.name}</h1>
      <p className="text-gray-600">
        {dm.title} @ {dm.company}
      </p>

      {/* TABS */}
      <DMDetailTabs dm={dm} />
    </div>
  );
}

