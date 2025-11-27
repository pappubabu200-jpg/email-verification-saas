"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  FiHome,
  FiMail,
  FiUpload,
  FiUsers,
  FiKey,
  FiDollarSign,
  FiDatabase,
  FiSettings,
  FiSearch,
} from "react-icons/fi";

export default function SideBar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const menu = [
    { label: "Dashboard", href: "/dashboard", icon: <FiHome /> },
    { label: "Verify Email", href: "/verification", icon: <FiMail /> },
    { label: "Bulk Jobs", href: "/bulk", icon: <FiUpload /> },
    {
      label: "Decision Maker",
      href: "/decision-maker",
      icon: <FiSearch />,
    },
    { label: "API Keys", href: "/api-keys", icon: <FiKey /> },
    { label: "Usage Logs", href: "/usage", icon: <FiDatabase /> },
    { label: "Billing", href: "/billing", icon: <FiDollarSign /> },
    { label: "Team", href: "/team", icon: <FiUsers /> },
    { label: "Settings", href: "/settings", icon: <FiSettings /> },
  ];

  return (
    <>
      {/* Mobile Toggle Button */}
      <button
        className="lg:hidden h-12 w-12 flex items-center justify-center fixed top-4 left-4 z-50 bg-white shadow-lg rounded-full"
        onClick={() => setOpen(!open)}
      >
        {open ? "✕" : "☰"}
      </button>

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 left-0 h-full bg-white border-r shadow-sm z-40 w-64 transform transition-transform duration-200 ${
          open ? "translate-x-0" : "-translate-x-64 lg:translate-x-0"
        }`}
      >
        <div className="h-16 flex items-center px-6 border-b">
          <span className="text-xl font-bold">ZeroVerify</span>
        </div>

        <nav className="mt-4 px-3 space-y-1">
          {menu.map((item) => {
            const active = pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-2 rounded-md text-sm font-medium transition ${
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <span className="text-lg">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
