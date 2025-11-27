"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import { useRouter } from "next/navigation";

export default function SendOtpPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const sendOtp = async () => {
    setLoading(true);
    setMsg("");
    setError("");

    try {
      await axios.post("/auth/send-otp", { email });
      setMsg("OTP sent! Check your business email.");
      router.push(`/auth/verify-otp?email=${encodeURIComponent(email)}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-16">
      <h1 className="text-3xl font-bold mb-6">Sign Up / Login</h1>
      <p className="mb-4 text-gray-500">Enter your business email</p>

      <input
        type="email"
        placeholder="you@company.com"
        className="border p-3 w-full rounded mb-4"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />

      <button
        disabled={loading}
        onClick={sendOtp}
        className="bg-blue-600 text-white px-4 py-2 rounded w-full"
      >
        {loading ? "Sending..." : "Send OTP"}
      </button>

      {msg && <p className="text-green-600 mt-4">{msg}</p>}
      {error && <p className="text-red-600 mt-4">{error}</p>}
    </div>
  );
        }
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "@/lib/axios";

// UI components (place under Frontend/components/ui/)
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function SendOtpPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // small client-side sanity check for email format
  const isValidEmail = (e: string) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);
  };

  const handleSendOtp = async () => {
    setError(null);
    setSuccess(null);

    const trimmed = (email || "").trim().toLowerCase();
    if (!trimmed) {
      setError("Please enter your business email.");
      return;
    }
    if (!isValidEmail(trimmed)) {
      setError("Please enter a valid email address.");
      return;
    }

    setLoading(true);
    try {
      await axios.post("/auth/send-otp", { email: trimmed });
      setSuccess("OTP sent — check your business email.");
      // navigate to verify page with email as query
      router.push(`/auth/verify-otp?email=${encodeURIComponent(trimmed)}`);
    } catch (err: any) {
      // prefer backend-provided message
      const detail = err?.response?.data?.detail || err?.message || "Failed to send OTP";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <main className="w-full max-w-md p-8">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold leading-tight">Sign up or log in</h1>
          <p className="text-sm text-gray-500 mt-2">
            Use your business email to receive a secure OTP. Personal inboxes are not allowed.
          </p>
        </div>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <div className="space-y-4">
          <Input
            label="Business email"
            type="email"
            value={email}
            onChange={(e: any) => setEmail(e.target.value)}
            placeholder="name@company.com"
            error={undefined}
          />

          <div>
            <Button
              onClick={handleSendOtp}
              variant="primary"
              disabled={loading}
              className="w-full"
            >
              {loading ? <div className="flex items-center gap-2"><Loader /> Sending...</div> : "Send OTP"}
            </Button>
          </div>

          <div className="text-xs text-gray-400 mt-2">
            By continuing you agree to our terms of service and privacy policy.
          </div>
        </div>
      </main>
    </div>
  );
}
