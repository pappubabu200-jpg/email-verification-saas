
"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import { useRouter, useSearchParams } from "next/navigation";

export default function SetPasswordPage() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setLoading(true);
    setErr("");

    try {
      const res = await axios.post("/auth/set-password", {
        otp_token: token,
        password,
      });

      // store JWTs
      localStorage.setItem("access_token", res.data.access_token);
      localStorage.setItem("refresh_token", res.data.refresh_token);

      router.push("/dashboard");
    } catch (error: any) {
      setErr(error.response?.data?.detail || "Failed to set password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-16">
      <h1 className="text-3xl font-bold mb-6">Create Password</h1>

      <input
        type="password"
        className="border p-3 w-full rounded mb-4"
        placeholder="Create strong password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      <button
        onClick={submit}
        className="bg-green-600 text-white px-4 py-2 rounded w-full"
        disabled={loading}
      >
        {loading ? "Saving..." : "Set Password & Continue"}
      </button>

      {err && <p className="text-red-600 mt-4">{err}</p>}
    </div>
  );
}

"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState } from "react";
import axios from "@/lib/axios";

import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";
import Loader from "@/components/ui/Loader";

export default function SetPasswordPage() {
  const params = useSearchParams();
  const router = useRouter();

  const email = params.get("email") || "";
  const userId = params.get("uid") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setSuccess(null);

    if (!password || !confirm) {
      setError("Password and confirmation are required.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);
    try {
      await axios.post("/auth/set-password", {
        user_id: Number(userId),
        password: password,
      });

      setSuccess("Password created successfully!");

      setTimeout(() => {
        router.push("/auth/login");
      }, 1000);
    } catch (err: any) {
      const detail = err.response?.data?.detail || "Failed to set password.";
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <main className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold mb-3">Create Password</h1>
        <p className="text-sm text-gray-600 mb-6">
          For: <b>{email}</b>
        </p>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <div className="space-y-4">
          <Input
            type="password"
            label="Password"
            placeholder="Enter new password"
            value={password}
            onChange={(e: any) => setPassword(e.target.value)}
          />

          <Input
            type="password"
            label="Confirm Password"
            placeholder="Re-enter password"
            value={confirm}
            onChange={(e: any) => setConfirm(e.target.value)}
          />

          <Button className="w-full" onClick={handleSubmit} disabled={loading}>
            {loading ? (
              <div className="flex items-center gap-2">
                <Loader /> Saving...
              </div>
            ) : (
              "Set Password"
            )}
          </Button>
        </div>
      </main>
    </div>
  );
  }
"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useState } from "react";
import axios from "@/lib/axios";

import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import ErrorBanner from "@/components/ui/ErrorBanner";
import SuccessBanner from "@/components/ui/SuccessBanner";

export default function SetPasswordPage() {
  const params = useSearchParams();
  const router = useRouter();

  const email = params.get("email") || "";
  const userId = params.get("uid") || "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setSuccess(null);

    if (password !== confirm) return setError("Passwords do not match.");
    if (password.length < 6) return setError("Password must be ≥ 6 characters.");

    setLoading(true);
    try {
      await axios.post("/auth/set-password", {
        user_id: Number(userId),
        password,
      });

      setSuccess("Password created!");

      setTimeout(() => router.push("/auth/login"), 800);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to set password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex justify-center items-center bg-gray-50">
      <div className="w-full max-w-md p-8">
        <h1 className="text-2xl font-semibold mb-3">Create Password</h1>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <div className="space-y-4">
          <Input
            type="password"
            label="Password"
            onChange={(e: any) => setPassword(e.target.value)}
          />

          <Input
            type="password"
            label="Confirm Password"
            onChange={(e: any) => setConfirm(e.target.value)}
          />

          <Button className="w-full" onClick={handleSubmit} disabled={loading}>
            {loading ? "Saving..." : "Set Password"}
          </Button>
        </div>
      </div>
    </div>
  );
}
