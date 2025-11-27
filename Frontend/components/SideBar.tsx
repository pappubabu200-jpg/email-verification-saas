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

"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  MailCheck,
  Upload,
  KeyRound,
  Users,
  CreditCard,
  Settings,
  Brain,
  ChevronLeft,
} from "lucide-react";
import { useState } from "react";

interface NavItem {
  label: string;
  href: string;
  icon: any;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: Home },
  { label: "Verify Email", href: "/verification", icon: MailCheck },
  { label: "Bulk Verification", href: "/bulk", icon: Upload },
  { label: "Decision Maker Finder", href: "/decision-maker", icon: Brain },
  { label: "API Keys", href: "/api-keys", icon: KeyRound },
  { label: "Team", href: "/team", icon: Users },
  { label: "Billing", href: "/billing", icon: CreditCard },
  { label: "Settings", href: "/settings", icon: Settings },
];

export default function SideBar() {
  const pathname = usePathname();
  const router = useRouter();

  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`
        h-screen bg-white border-r shadow-sm flex flex-col transition-all duration-200
        ${collapsed ? "w-16" : "w-64"}
      `}
    >
      {/* Header Logo + Collapse Button */}
      <div className="flex items-center justify-between px-4 h-14 border-b">
        <span
          className={`font-bold text-xl text-gray-800 transition-opacity ${
            collapsed ? "opacity-0 hidden" : "opacity-100"
          }`}
        >
          ZeroVerify
        </span>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-2 hover:bg-gray-100 rounded-md"
        >
          <ChevronLeft
            size={20}
            className={`${collapsed ? "rotate-180" : ""} transition-transform`}
          />
        </button>
      </div>

      {/* Navigation Links */}
      <nav className="mt-4 flex-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);

          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={`
                w-full flex items-center gap-3 px-4 py-3 text-left transition-all
                ${
                  active
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-100"
                }
              `}
            >
              <Icon size={20} />
              {!collapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
