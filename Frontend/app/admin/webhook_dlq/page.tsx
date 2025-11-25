
"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";   // your preconfigured Axios instance
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/use-toast";
import { ReloadIcon } from "@radix-ui/react-icons";

interface DLQEntry {
  id: number;
  url: string;
  payload: any;
  headers: any;
  error: string;
  attempts: number;
  created_at: string;
}

export default function WebhookDLQPage() {
  const [items, setItems] = useState<DLQEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [retryingId, setRetryingId] = useState<number | null>(null);
  const [pageLimit] = useState(50);

  // load DLQ entries
  const loadData = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/admin/webhook-dlq?limit=${pageLimit}`);
      setItems(res.data.results || []);
    } catch (err: any) {
      toast({
        title: "Error",
        description: "Failed to load DLQ items",
        variant: "destructive",
      });
    }
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Retry one
  const retryOne = async (id: number) => {
    setRetryingId(id);
    try {
      await axios.post(`/admin/webhook-dlq/requeue/${id}`);
      toast({ title: "Requeued", description: `Entry ${id} requeued` });
      loadData();
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to requeue entry",
        variant: "destructive",
      });
    }
    setRetryingId(null);
  };

  // Retry all
  const retryAll = async () => {
    setLoading(true);
    try {
      await axios.post(`/admin/webhook-dlq/requeue-all`);
      toast({ title: "Requeued All", description: "All DLQ entries have been queued." });
      loadData();
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to requeue all entries",
        variant: "destructive",
      });
    }
    setLoading(false);
  };

  // Delete entry
  const deleteEntry = async (id: number) => {
    try {
      await axios.delete(`/admin/webhook-dlq/${id}`);
      toast({ title: "Deleted", description: `Entry ${id} deleted` });
      loadData();
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to delete entry",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Webhook DLQ</h1>
        
        <Button onClick={retryAll} disabled={loading}>
          {loading ? (
            <ReloadIcon className="mr-2 h-4 w-4 animate-spin" />
          ) : null}
          Retry All
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <ReloadIcon className="h-6 w-6 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-gray-500">No DLQ entries found — all webhooks are healthy!</p>
      ) : (
        <div className="grid gap-4">
          {items.map((item) => (
            <Card key={item.id} className="border border-gray-300">
              <CardContent className="p-4 space-y-3">
                <div className="flex justify-between">
                  <div>
                    <p className="text-sm text-gray-600">Entry ID</p>
                    <p className="font-semibold">{item.id}</p>
                  </div>
                  <Badge variant="destructive">Failed</Badge>
                </div>

                <div>
                  <p className="text-sm text-gray-600">Webhook URL</p>
                  <p className="font-mono text-sm break-all">{item.url}</p>
                </div>

                <div>
                  <p className="text-sm text-gray-600">Error</p>
                  <p className="text-red-700 text-sm">{item.error}</p>
                </div>

                <div>
                  <p className="text-sm text-gray-600">Attempts</p>
                  <p className="font-semibold">{item.attempts}</p>
                </div>

                <div className="flex gap-3 pt-3">
                  <Button
                    variant="outline"
                    onClick={() => retryOne(item.id)}
                    disabled={retryingId === item.id}
                  >
                    {retryingId === item.id ? (
                      <ReloadIcon className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    Retry
                  </Button>

                  <Button
                    variant="destructive"
                    onClick={() => deleteEntry(item.id)}
                  >
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
        }
