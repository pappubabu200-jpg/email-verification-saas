"use client";

import React from "react";
import Link from "next/link";
import { Mail, Building2, Briefcase, ArrowRight, ShieldCheck } from "lucide-react";
import { DecisionMakerResult } from "@/lib/api/decision_maker";

export default function DMResultCard({ dm }: { dm: DecisionMakerResult }) {
  return (
    <div className="p-5 border rounded-xl shadow-sm hover:shadow-md transition bg-white flex justify-between items-start">
      
      {/* LEFT INFO */}
      <div>
        <h2 className="text-lg font-semibold">{dm.name}</h2>

        {dm.title && (
          <p className="text-sm text-gray-600 flex items-center gap-2 mt-1">
            <Briefcase size={16} />
            {dm.title}
          </p>
        )}

        {dm.company && (
          <p className="text-sm text-gray-600 flex items-center gap-2 mt-1">
            <Building2 size={16} />
            {dm.company}
          </p>
        )}

        {dm.email && (
          <p className="text-sm text-gray-800 flex items-center gap-2 mt-1 font-medium">
            <Mail size={16} />
            {dm.email}
          </p>
        )}

        {dm.confidence !== undefined && (
          <p className="text-xs text-gray-500 flex items-center gap-2 mt-2">
            <ShieldCheck size={14} className="text-green-600" />
            Confidence Score: <b>{dm.confidence}%</b>
          </p>
        )}
      </div>

      {/* RIGHT BUTTON */}
      <Link
        href={`/decision-maker/${dm.id}`}
        className="flex items-center gap-1 text-blue-600 font-semibold hover:underline"
      >
        View
        <ArrowRight size={16} />
      </Link>

    </div>
  );
}

"use client";

import { useState } from "react";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import axios from "@/lib/axios";

export default function DMResultCard({ item, onClose }: { item: any; onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [enriched, setEnriched] = useState<any>(item);

  const triggerEnrich = async () => {
    setLoading(true);
    try {
      const res = await axios.post("/decision-maker/enrich", { id: item.id || item.email });
      // API may respond sync or queue; optimistic update
      setEnriched((prev: any) => ({ ...prev, enrichment_status: "queued" }));
    } catch (err) {
      console.error("Enrich failed", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/30" onClick={onClose}></div>
      <div className="relative w-full max-w-3xl">
        <Card className="p-6">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-xl font-semibold">{enriched.name || enriched.email}</h2>
              <p className="text-sm text-gray-500">{enriched.title || ""}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onClose}>Close</Button>
              <Button onClick={triggerEnrich} disabled={loading}>
                {loading ? "Enriching..." : "Run Enrichment"}
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
            <div>
              <p className="text-xs text-gray-500">Email</p>
              <p className="font-medium">{enriched.email || "-"}</p>

              <p className="text-xs text-gray-500 mt-3">Phone</p>
              <p className="font-medium">{enriched.phone || "-"}</p>

              <p className="text-xs text-gray-500 mt-3">Location</p>
              <p className="font-medium">{enriched.location || "-"}</p>
            </div>

            <div>
              <p className="text-xs text-gray-500">Company</p>
              <p className="font-medium">{enriched.company || "-"}</p>

              <p className="text-xs text-gray-500 mt-3">Seniority</p>
              <p className="font-medium">{enriched.seniority || "-"}</p>

              <p className="text-xs text-gray-500 mt-3">LinkedIn</p>
              <p className="text-sm text-blue-600">
                {enriched.linkedin ? <a target="_blank" href={enriched.linkedin}>View</a> : "-"}
              </p>
            </div>
          </div>

          {enriched.enrichment && (
            <div className="mt-6 bg-gray-50 p-3 rounded text-sm">
              <pre className="whitespace-pre-wrap text-xs">{JSON.stringify(enriched.enrichment, null, 2)}</pre>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
