
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
