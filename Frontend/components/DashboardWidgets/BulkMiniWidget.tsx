"use client";

import Card from "@/components/ui/Card";
import useVerificationStream from "@/hooks/useVerificationStream";

export default function BulkMiniWidget({ userId }: { userId: string }) {
  const { bulkJobs } = useVerificationStream(userId);

  const lastJobId = Object.keys(bulkJobs).pop();
  const lastJob = lastJobId ? bulkJobs[lastJobId] : null;

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold mb-2">Bulk Job Progress</h2>

      {!lastJob ? (
        <p className="text-gray-500 text-sm">No bulk jobs yet</p>
      ) : (
        <div className="space-y-2">
          <p className="text-sm">
            Job: <b>{lastJob.job_id}</b>
          </p>

          <p className="text-sm text-gray-600">
            {lastJob.processed}/{lastJob.total} processed
          </p>

          <div className="w-full h-2 bg-gray-200 rounded">
            <div
              className="bg-blue-600 h-full rounded"
              style={{
                width: `${Math.round((lastJob.processed / lastJob.total) * 100)}%`,
              }}
            ></div>
          </div>

          <p className="text-xs text-gray-400">
            Valid: {lastJob.stats?.valid} | Invalid: {lastJob.stats?.invalid}
          </p>
        </div>
      )}
    </Card>
  );
}
