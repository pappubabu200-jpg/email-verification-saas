
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
