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
