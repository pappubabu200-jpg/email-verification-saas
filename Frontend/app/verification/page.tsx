"use client";

import { useState } from "react";
import axios from "@/lib/axios";

import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function SingleVerificationPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const verifyEmail = async () => {
    setError(null);
    setResult(null);

    if (!email.includes("@")) {
      setError("Enter a valid email address.");
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post("/verification/verify", { email });

      setResult(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-8">
      <h1 className="text-3xl font-semibold">Verify a Single Email</h1>
      <p className="text-gray-600">Check email validity, SMTP response, risk score, and domain reputation instantly.</p>

      {/* Email Input */}
      <Card>
        <div className="space-y-4">
          <Input
            label="Email address"
            value={email}
            onChange={(e: any) => setEmail(e.target.value)}
            placeholder="user@example.com"
          />

          <Button onClick={verifyEmail} className="w-full" disabled={loading}>
            {loading ? (
              <div className="flex items-center gap-2">
                <Loader /> Verifying...
              </div>
            ) : (
              "Verify Email"
            )}
          </Button>

          {error && <ErrorBanner message={error} />}
        </div>
      </Card>

      {/* Result */}
      {result && (
        <Card>
          <h2 className="text-xl font-semibold mb-4">Verification Result</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Status */}
            <div>
              <p className="text-sm text-gray-500">Status</p>
              <p className={`text-2xl font-bold ${
                result.status === "valid"
                  ? "text-green-600"
                  : result.status === "invalid"
                  ? "text-red-600"
                  : "text-yellow-600"
              }`}>
                {result.status?.toUpperCase()}
              </p>
            </div>

            {/* Risk Score */}
            <div>
              <p className="text-sm text-gray-500">Risk Score</p>
              <p className="text-2xl font-bold">{result.risk_score ?? "--"}</p>
            </div>

            {/* Domain Reputation */}
            <div>
              <p className="text-sm text-gray-500">Domain Reputation</p>
              <p className="text-2xl font-bold">{result.domain_reputation ?? "--"}</p>
            </div>

            {/* Cached */}
            <div>
              <p className="text-sm text-gray-500">Cached</p>
              <p className="text-2xl font-bold">{result.cached ? "Yes" : "No"}</p>
            </div>
          </div>

          {/* SMTP Details */}
          <div className="mt-6">
            <p className="text-sm text-gray-500">SMTP Response</p>
            <pre className="bg-gray-100 p-3 rounded text-sm mt-1 whitespace-pre-wrap">
              {JSON.stringify(result.smtp_raw || result.raw || result, null, 2)}
            </pre>
          </div>
        </Card>
      )}
    </div>
  );
  }
