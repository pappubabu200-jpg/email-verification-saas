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
