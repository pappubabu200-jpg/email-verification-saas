"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "@/lib/axios";

import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";
import Loader from "@/components/ui/Loader";

export default function OtpUnifiedPage() {
  const router = useRouter();

  // UI State
  const [step, setStep] = useState<1 | 2>(1); // 1 = email, 2 = otp
  const [loading, setLoading] = useState(false);

  // Form State
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");

  // Messages
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // -------------------------------
  // STEP 1: Send OTP to email
  // -------------------------------
  const handleSendOtp = async () => {
    setError(null);
    setSuccess(null);

    const trimmed = email.trim().toLowerCase();
    if (!trimmed) return setError("Please enter an email address.");
    if (!/^[^@]+@[^@]+\.[^@]+$/.test(trimmed))
      return setError("Enter a valid business email.");

    setLoading(true);

    try {
      await axios.post("/auth/send-otp", { email: trimmed });
      setSuccess("OTP sent — check your business email.");
      setStep(2); // Move to OTP screen
    } catch (err: any) {
      const detail = err.response?.data?.detail || "Failed to send OTP";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  // -------------------------------
  // STEP 2: Verify OTP
  // -------------------------------
  const handleVerifyOtp = async () => {
    setError(null);
    setSuccess(null);

    if (!otp) return setError("Enter the OTP sent to your email.");

    setLoading(true);

    try {
      const res = await axios.post("/auth/verify-otp", {
        email: email.trim().toLowerCase(),
        otp: otp.trim(),
      });

      const { user_id } = res.data;

      setSuccess("OTP verified successfully!");

      setTimeout(() => {
        router.push(
          `/auth/set-password?uid=${user_id}&email=${encodeURIComponent(email)}`
        );
      }, 800);
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Invalid OTP";
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  // -----------------------------------------------------
  // RENDER UI
  // -----------------------------------------------------
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <main className="w-full max-w-md p-8">

        {/* Title */}
        <h1 className="text-2xl font-semibold mb-2">
          {step === 1 ? "Sign up / Login" : "Verify OTP"}
        </h1>

        <p className="text-gray-500 mb-6">
          {step === 1
            ? "Enter your business email to receive a verification code."
            : `We sent a 6-digit OTP to ${email}`}
        </p>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        {/* -------------------- STEP 1 -------------------- */}
        {step === 1 && (
          <div className="space-y-4">
            <Input
              label="Business Email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e: any) => setEmail(e.target.value)}
            />

            <Button
              className="w-full"
              onClick={handleSendOtp}
              disabled={loading}
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <Loader /> Sending...
                </div>
              ) : (
                "Send OTP"
              )}
            </Button>
          </div>
        )}

        {/* -------------------- STEP 2 -------------------- */}
        {step === 2 && (
          <div className="space-y-4">
            <Input
              label="OTP"
              type="text"
              placeholder="6-digit code"
              value={otp}
              onChange={(e: any) => setOtp(e.target.value)}
            />

            <Button
              className="w-full"
              onClick={handleVerifyOtp}
              disabled={loading}
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <Loader /> Verifying...
                </div>
              ) : (
                "Verify OTP"
              )}
            </Button>

            <p
              className="text-sm text-blue-600 underline cursor-pointer text-center"
              onClick={handleSendOtp}
            >
              Resend OTP
            </p>
          </div>
        )}

        {/* Footer */}
        <p className="text-xs text-gray-400 mt-6 text-center">
          By continuing you agree to our Terms & Privacy.
        </p>
      </main>
    </div>
  );
}
