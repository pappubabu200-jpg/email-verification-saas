"use client";

import dynamic from "next/dynamic";
import Card from "@/components/ui/Card";

// Recharts — dynamically imported (Next.js recommended)
const LineChart = dynamic(
  () => import("recharts").then((mod) => mod.LineChart),
  { ssr: false }
);
const Line = dynamic(
  () => import("recharts").then((mod) => mod.Line),
  { ssr: false }
);
const XAxis = dynamic(
  () => import("recharts").then((mod) => mod.XAxis),
  { ssr: false }
);
const YAxis = dynamic(
  () => import("recharts").then((mod) => mod.YAxis),
  { ssr: false }
);
const Tooltip = dynamic(
  () => import("recharts").then((mod) => mod.Tooltip),
  { ssr: false }
);
const ResponsiveContainer = dynamic(
  () => import("recharts").then((mod) => mod.ResponsiveContainer),
  { ssr: false }
);

export default function UsageChart({ data }: { data: any[] }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-gray-500">Last 7 Days Usage</p>

      <div style={{ width: "100%", height: 150 }}>
        <ResponsiveContainer>
          <LineChart data={data}>
            <XAxis dataKey="date" stroke="#888" fontSize={12} />
            <YAxis stroke="#888" fontSize={12} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="count"
              stroke="#2563eb"
              strokeWidth={3}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
