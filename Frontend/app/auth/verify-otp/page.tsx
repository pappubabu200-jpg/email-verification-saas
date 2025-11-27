"use client";

import { useState, useEffect } from "react";
import axios from "@/lib/axios";
import { useRouter, useSearchParams } from "next/navigation";

export default function VerifyOtpPage() {
  const router = useRouter();
  const params = useSearchParams();

  const emailFromQuery = params.get("email") || "";
  const [email, setEmail] = useState(emailFromQuery);
  const [otp, setOtp] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => setEmail(emailFromQuery), [emailFromQuery]);

  const verifyOtp = async () => {
    setLoading(true);
    setError("");

    try {
      const res = await axios.post("/auth/verify-otp", { email, otp });
      const { otp_token, user_exists } = res.data;

      if (user_exists) {
        router.push(`/auth/login-password?token=${otp_token}`);
      } else {
        router.push(`/auth/set-password?token=${otp_token}`);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Invalid OTP");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-16">
      <h1 className="text-3xl font-bold mb-6">Verify OTP</h1>
      <p className="mb-3 text-gray-500">OTP sent to: {email}</p>

      <input
        type="text"
        maxLength={6}
        placeholder="Enter OTP"
        className="border p-3 w-full rounded mb-4"
        value={otp}
        onChange={(e) => setOtp(e.target.value)}
      />

      <button
        disabled={loading}
        onClick={verifyOtp}
        className="bg-blue-600 text-white px-4 py-2 rounded w-full"
      >
        {loading ? "Verifying..." : "Verify OTP"}
      </button>

      {error && <p className="text-red-600 mt-4">{error}</p>}
    </div>
  );
          }
"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import axios from "@/lib/axios";

import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function VerifyOtpPage() {
  const params = useSearchParams();
  const router = useRouter();

  const emailFromQuery = params.get("email") || "";
  const [email, setEmail] = useState(emailFromQuery);
  const [otp, setOtp] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (emailFromQuery) {
      setEmail(emailFromQuery);
    }
  }, [emailFromQuery]);

  const handleVerify = async () => {
    setError(null);
    setSuccess(null);

    if (!email || !otp) {
      setError("Email and OTP are required.");
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post("/auth/verify-otp", {
        email: email,
        otp: otp,
        create_team: true,
      });

      setSuccess("OTP verified successfully!");
      const userId = res.data?.user_id;

      // redirect to set password page
      setTimeout(() => {
        router.push(`/auth/set-password?email=${encodeURIComponent(email)}&uid=${userId}`);
      }, 800);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Invalid OTP.";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <main className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold mb-4">Verify OTP</h1>
        <p className="text-sm text-gray-500 mb-6">Enter the 6-digit code sent to your business email.</p>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <div className="space-y-4">
          <Input
            label="Business email"
            type="email"
            value={email}
            onChange={(e: any) => setEmail(e.target.value)}
            placeholder="name@company.com"
            disabled
          />

          <Input
            label="OTP"
            type="text"
            value={otp}
            maxLength={6}
            onChange={(e: any) => setOtp(e.target.value)}
            placeholder="123456"
          />

          <Button onClick={handleVerify} disabled={loading} className="w-full">
            {loading ? <div className="flex items-center gap-2"><Loader /> Verifying...</div> : "Verify OTP"}
          </Button>

          <button
            onClick={() => router.push(`/auth/send-otp`)}
            className="text-sm text-blue-600 underline mt-3"
          >
            Resend OTP
          </button>
        </div>
      </main>
    </div>
  );
                                                                   }
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "@/lib/axios";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function VerifyOtpPage() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleVerify = async () => {
    setError(null);
    setSuccess(null);

    if (!email || !otp) return setError("Enter email & OTP");

    setLoading(true);
    try {
      const res = await axios.post("/auth/verify-otp", {
        email: email.trim(),
        otp: otp.trim(),
      });

      const { user_id, email: e } = res.data;

      setSuccess("OTP verified!");
      setTimeout(() => {
        router.push(`/auth/set-password?uid=${user_id}&email=${e}`);
      }, 800);
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Invalid OTP";
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex justify-center items-center bg-gray-50">
      <div className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold mb-4">Verify OTP</h1>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <div className="space-y-4">
          <Input
            label="Email"
            type="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e: any) => setEmail(e.target.value)}
          />

          <Input
            label="OTP"
            type="text"
            placeholder="6 digit code"
            value={otp}
            onChange={(e: any) => setOtp(e.target.value)}
          />

          <Button className="w-full" onClick={handleVerify} disabled={loading}>
            {loading ? "Verifying..." : "Verify OTP"}
          </Button>
        </div>
      </div>
    </div>
  );
}

