"use client";

import Card from "@/components/ui/Card";

export default function CreditsCard({ credits }: { credits: number }) {
  return (
    <Card className="p-6 flex flex-col justify-between">
      <p className="text-sm text-gray-500">Credits Remaining</p>

      <h2 className="text-4xl font-bold mt-2">
        {credits.toLocaleString()}
      </h2>

      <p className="text-xs text-gray-400 mt-2">
        Credits auto-refresh every 5 seconds
      </p>
    </Card>
  );
}
