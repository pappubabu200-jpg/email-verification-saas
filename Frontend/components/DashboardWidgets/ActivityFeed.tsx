
"use client";

import Card from "@/components/ui/Card";
import useVerificationStream from "@/hooks/useVerificationStream";

export default function ActivityFeed({ userId }: { userId: string }) {
  const { events } = useVerificationStream(userId);

  return (
    <Card className="p-6 max-h-96 overflow-y-auto">
      <h2 className="text-lg font-semibold mb-4">Activity Feed</h2>

      {events.length === 0 && (
        <p className="text-sm text-gray-500">No events yet</p>
      )}

      <ul className="space-y-3">
        {events.map((ev, idx) => (
          <li key={idx} className="border-b pb-2 text-sm">
            <span className="font-medium">{ev.type}</span>
            <div className="text-gray-600">
              {ev.email || ev.message || ev.job_id}
            </div>
            <div className="text-xs text-gray-400">
              {new Date(ev.ts).toLocaleString()}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
