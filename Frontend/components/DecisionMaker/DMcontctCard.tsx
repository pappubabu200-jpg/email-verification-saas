"use client";

import Card from "@/components/ui/Card";
import Link from "next/link";

export default function DMContactCard({ dm }: { dm: any }) {
  const person = dm.profile || {};
  const company = dm.company || {};

  const scoreColor =
    dm.confidence >= 80
      ? "bg-green-500"
      : dm.confidence >= 50
      ? "bg-yellow-500"
      : "bg-red-500";

  return (
    <Card className="p-6">
      <div className="flex items-center gap-6">
        {/* Avatar */}
        <div className="rounded-full h-20 w-20 bg-gray-200 flex items-center justify-center text-3xl">
          {person.name?.charAt(0)}
        </div>

        {/* Basic Info */}
        <div className="flex-1">
          <h1 className="text-2xl font-semibold">{person.name}</h1>
          <p className="text-gray-600">{person.title}</p>
          <p className="text-gray-500">{company.name}</p>

          {/* Confidence Badge */}
          <div className="flex items-center gap-2 mt-2">
            <span className={`text-xs px-2 py-1 rounded text-white ${scoreColor}`}>
              Confidence: {dm.confidence ?? "?"}%
            </span>
          </div>
        </div>
      </div>

      {/* Contact Info */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
        <div>
          <p className="text-xs text-gray-500">Email</p>
          <p className="font-medium break-words">{person.email || "Not available"}</p>
        </div>

        <div>
          <p className="text-xs text-gray-500">Phone</p>
          <p className="font-medium">{person.phone || "Not available"}</p>
        </div>
      </div>

      {/* Social Links */}
      <div className="flex gap-4 mt-4">
        {person.linkedin && (
          <a
            href={person.linkedin}
            target="_blank"
            className="text-blue-600 hover:underline"
          >
            LinkedIn
          </a>
        )}
        {person.twitter && (
          <a
            href={person.twitter}
            target="_blank"
            className="text-blue-400 hover:underline"
          >
            Twitter
          </a>
        )}
      </div>
    </Card>
  );
}
