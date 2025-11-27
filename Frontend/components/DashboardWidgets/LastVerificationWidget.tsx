
"use client";

import Card from "@/components/ui/Card";
import useVerificationStream from "@/hooks/useVerificationStream";

export default function LastVerificationWidget({ userId }: { userId: string }) {
  const { lastVerification } = useVerificationStream(userId);

  if (!lastVerification) {
    return (
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-2">Last Verification</h2>
        <p className="text-gray-500 text-sm">No verifications yet</p>
      </Card>
    );
  }

  const { email, status, score, ts } = lastVerification;

  return (
    <Card className="p-6 space-y-2">
      <h2 className="text-lg font-semibold">Last Verification</h2>

      <p className="text-sm font-medium">{email}</p>

      <p
        className={
          status === "valid"
            ? "text-green-600"
            : status === "risky"
            ? "text-yellow-600"
            : "text-red-600"
        }
      >
        {status.toUpperCase()}
      </p>

      <p className="text-gray-500 text-sm">Risk Score: {score}</p>
      <p className="text-gray-400 text-xs">{new Date(ts).toLocaleString()}</p>
    </Card>
  );
}
