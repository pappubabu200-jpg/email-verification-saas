"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";

export default function BillingAdminPage() {
  const [plans, setPlans] = useState<any[]>([]);
  const [subs, setSubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const p = await axios.get("/admin/plans");
      const s = await axios.get("/admin/subscriptions");

      setPlans(p.data);
      setSubs(s.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (loading) return <Loader />;

  return (
    <div className="max-w-6xl mx-auto p-8 space-y-8">
      <h1 className="text-2xl font-semibold">Billing</h1>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Plans</h2>

        <ul className="space-y-2">
          {plans.map((p) => (
            <li key={p.id}>
              <b>{p.name}</b> — {p.price} / {p.interval}
            </li>
          ))}
        </ul>
      </Card>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Subscriptions</h2>

        <ul className="space-y-2">
          {subs.map((s) => (
            <li key={s.id}>
              User {s.user_id} — {s.plan_name} — status: {s.status}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
