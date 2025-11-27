"use client";

import Card from "@/components/ui/Card";
import dynamic from "next/dynamic";

const RadialBarChart = dynamic(
  () => import("recharts").then((mod) => mod.RadialBarChart),
  { ssr: false }
);
const RadialBar = dynamic(
  () => import("recharts").then((mod) => mod.RadialBar),
  { ssr: false }
);
const ResponsiveContainer = dynamic(
  () => import("recharts").then((mod) => mod.ResponsiveContainer),
  { ssr: false }
);

export default function DeliverabilityChart({ value }: { value: number }) {
  const chartData = [
    {
      name: "Deliverability",
      value,
      fill: "#22c55e",
    },
  ];

  return (
    <Card className="p-6">
      <p className="text-sm text-gray-500">Deliverability Score</p>

      <div style={{ width: "100%", height: 150 }}>
        <ResponsiveContainer>
          <RadialBarChart
            cx="50%"
            cy="50%"
            innerRadius="60%"
            outerRadius="100%"
            barSize={12}
            data={chartData}
          >
            <RadialBar minAngle={15} background clockWise dataKey="value" />
          </RadialBarChart>
        </ResponsiveContainer>
      </div>

      <p className="text-center text-2xl font-semibold mt-2">
        {value}%
      </p>

      <p className="text-xs text-gray-400 text-center">
        Real-time deliverability index
      </p>
    </Card>
  );
}
