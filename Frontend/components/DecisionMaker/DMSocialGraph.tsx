"use client";

import Card from "@/components/ui/Card";
import Link from "next/link";

export default function DMSocialGraph({ dm }: { dm: any }) {
  const { org } = dm; // backend should return org graph if available

  if (!org) return null;

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold mb-4">Social Graph</h2>

      {/* Manager */}
      {org.manager && (
        <div className="mb-6">
          <p className="text-xs text-gray-500 mb-1">Manager</p>
          <Link
            className="text-blue-600 hover:underline font-medium"
            href={`/decision-maker/${org.manager.id}`}
          >
            {org.manager.name} — {org.manager.title}
          </Link>
        </div>
      )}

      {/* Peers */}
      {org.peers?.length > 0 && (
        <div className="mb-6">
          <p className="text-xs text-gray-500 mb-1">Peers</p>
          <div className="space-y-1">
            {org.peers.map((peer: any) => (
              <Link
                key={peer.id}
                className="text-blue-600 hover:underline"
                href={`/decision-maker/${peer.id}`}
              >
                {peer.name} — {peer.title}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Direct Reports */}
      {org.reports?.length > 0 && (
        <div className="mb-6">
          <p className="text-xs text-gray-500 mb-1">Direct Reports</p>
          <div className="space-y-1">
            {org.reports.map((rep: any) => (
              <Link
                key={rep.id}
                className="text-blue-600 hover:underline"
                href={`/decision-maker/${rep.id}`}
              >
                {rep.name} — {rep.title}
              </Link>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
