"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginPasswordPage() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const login = async () => {
    setErr("");
    setLoading(true);

    try {
      const res = await axios.post("/auth/login-password", {
        otp_token: token,
        password,
      });

      localStorage.setItem("access_token", res.data.access_token);
      localStorage.setItem("refresh_token", res.data.refresh_token);

      router.push("/dashboard");
    } catch (error: any) {
      setErr(error.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-16">
      <h1 className="text-3xl font-bold mb-6">Enter Password</h1>

      <input
        type="password"
        className="border p-3 w-full rounded mb-4"
        placeholder="Your password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      <button
        onClick={login}
        className="bg-blue-600 text-white px-4 py-2 rounded w-full"
        disabled={loading}
      >
        {loading ? "Logging in..." : "Login"}
      </button>

      {err && <p className="text-red-600 mt-4">{err}</p>}
    </div>
  );
}
