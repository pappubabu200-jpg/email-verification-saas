
"use client";

import SideBar from "@/components/SideBar";
import NavBar from "@/components/NavBar";
import ProtectedRoute from "@/components/ProtectedRoute";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <div className="flex w-full h-screen overflow-hidden">
        {/* Sidebar */}
        <SideBar />

        {/* Main Area */}
        <div className="flex flex-col flex-1 overflow-hidden ml-0 lg:ml-64">

          {/* Top Navigation */}
          <NavBar />

          {/* Page Content */}
          <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
            {children}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
"use client";

import SideBar from "@/components/SideBar";
import NavBar from "@/components/NavBar";
import { useAuth } from "@/hooks/useAuth";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading } = useAuth();

  // Redirect unauthenticated users
  useEffect(() => {
    if (!loading && !user) {
      router.push("/auth/send-otp");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex items-center justify-center h-screen text-gray-600">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Left Sidebar */}
      <SideBar />

      {/* Main Area */}
      <div className="flex flex-col flex-1">
        {/* Top Navigation Bar */}
        <NavBar />

        {/* Page Content */}
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
