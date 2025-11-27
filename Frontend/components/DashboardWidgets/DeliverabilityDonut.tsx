
"use client";

import Card from "@/components/ui/Card";
import useVerificationStream from "@/hooks/useVerificationStream";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

const COLORS = ["#16a34a", "#f59e0b", "#ef4444", "#3b82f6"];

export default function DeliverabilityDonut({ userId }: { userId: string }) {
  const { riskChart } = useVerificationStream(userId);

  const data = [
    { name: "Valid", value: riskChart.valid },
    { name: "Risky", value: riskChart.risky },
    { name: "Invalid", value: riskChart.invalid },
    { name: "Unknown", value: riskChart.unknown },
  ];

  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold mb-4">Deliverability Breakdown</h2>

      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              innerRadius={50}
              outerRadius={80}
              paddingAngle={3}
            >
              {data.map((entry, index) => (
                <Cell key={index} fill={COLORS[index]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm text-gray-600 mt-4">
        {data.map((d, i) => (
          <p key={i}>
            <span className="font-medium">{d.name}:</span> {d.value}
          </p>
        ))}
      </div>
    </Card>
  );
}
