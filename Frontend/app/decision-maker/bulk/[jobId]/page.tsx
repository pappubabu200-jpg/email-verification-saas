// Frontend/app/decision-maker/bulk/[jobId]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import axios from "@/lib/axios";
import Loader from "@/components/ui/Loader";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import { useDMBulkWS } from "@/hooks/useDMBulkWS";

export default function DMBulkJobDetailPage() {
  const { jobId } = useParams();
  const [job, setJob] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const wsEvent = useDMBulkWS(jobId as string);

  const load = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/dm/bulk/${jobId}`);
      setJob(res.data);
    } catch (err) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [jobId]);

  useEffect(() => {
    if (!wsEvent) return;
    if (wsEvent.event === "progress") {
      setJob((p:any)=> ({ ...(p||{}), processed: wsEvent.processed, total: wsEvent.total }));
    }
    if (wsEvent.event === "completed") {
      setJob((p:any)=> ({ ...(p||{}), status: "finished", processed: wsEvent.processed, total: wsEvent.total }));
      // reload final
      load();
    }
    if (wsEvent.event === "failed") {
      setJob((p:any)=> ({ ...(p||{}), status: "failed" }));
    }
  }, [wsEvent]);

  if (loading) return <div className="p-8"><Loader /></div>;
  if (!job) return <div className="p-8 text-red-600">Job not found</div>;

  const progress = job.total ? Math.round((job.processed||0)/(job.total||1)*100) : 0;

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Bulk Discovery — {job.job_id}</h1>
          <p className="text-sm text-gray-500">Status: {job.status}</p>
        </div>
        <div>
          <Button onClick={load}>Refresh</Button>
        </div>
      </div>

      <Card className="p-6">
        <div className="mb-3">Progress: {job.processed || 0} / {job.total || 0} ({progress}%)</div>
        <div className="w-full bg-gray-200 h-3 rounded">
          <div className="h-full bg-blue-600" style={{width:`${progress}%`}}/>
        </div>
      </Card>

      <Card className="p-6">
        <h3 className="font-semibold mb-3">Recent outputs (preview)</h3>
        <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto">{JSON.stringify(job.results_preview||job.output_preview||{}, null, 2)}</pre>
      </Card>

      {job.status === "finished" && job.output_path && (
        <Card className="p-6">
          <Button onClick={()=>window.open(job.output_path)}>Open Results</Button>
        </Card>
      )}
    </div>
  );
}
