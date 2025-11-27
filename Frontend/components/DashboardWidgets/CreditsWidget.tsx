"use client";

import Card from "@/components/ui/Card";
import useVerificationStream from "@/hooks/useVerificationStream";

export default function CreditsWidget({ userId }: { userId: string }) {
  const { credits } = useVerificationStream(userId);

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold mb-2">Credits Remaining</h2>

      <div className="text-4xl font-bold text-blue-600">
        {credits ? credits.remaining.toLocaleString() : "—"}
      </div>

      <p className="text-sm text-gray-500">
        Reserved: {credits ? credits.reserved.toLocaleString() : "—"}
      </p>
    </Card>
  );
}
