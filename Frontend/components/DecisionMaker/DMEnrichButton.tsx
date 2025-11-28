"use client";

import { useState } from "react";
import axios from "@/lib/axios";
import Button from "@/components/ui/Button";
import Loader from "@/components/ui/Loader";

export default function DMEnrichButton({
  dmId,
  onStart,
}: {
  dmId: string;
  onStart?: (taskId: string) => void;
}) {
  const [loading, setLoading] = useState(false);

  const startEnrich = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`/decision-maker/${dmId}/enrich`);
      const taskId = res.data.task_id;

      if (onStart) onStart(taskId);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to start enrichment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button onClick={startEnrich} disabled={loading} variant="primary">
      {loading ? (
        <div className="flex items-center gap-2">
          <Loader /> Starting...
        </div>
      ) : (
        "Enrich Profile"
      )}
    </Button>
  );
}
