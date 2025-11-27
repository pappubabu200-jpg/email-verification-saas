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
