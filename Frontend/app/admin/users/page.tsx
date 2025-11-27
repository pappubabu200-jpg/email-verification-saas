"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadUsers = async () => {
    try {
      const res = await axios.get("/admin/users");
      setUsers(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  if (loading) return <Loader />;

  return (
    <div className="max-w-6xl mx-auto p-8">
      <h1 className="text-2xl font-semibold mb-6">Users</h1>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm border-collapse">
          <thead className="bg-gray-100">
            <tr>
              <th className="p-3 text-left">ID</th>
              <th className="p-3">Email</th>
              <th className="p-3">Verified</th>
              <th className="p-3">Credits</th>
              <th className="p-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u: any) => (
              <tr key={u.id} className="border-b hover:bg-gray-50">
                <td className="p-3">{u.id}</td>
                <td className="p-3">{u.email}</td>
                <td className="p-3">{u.email_verified ? "Yes" : "No"}</td>
                <td className="p-3">{u.credits}</td>
                <td className="p-3">
                  {new Date(u.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
