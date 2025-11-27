"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import useAuth from "@/hooks/useAuth";
import Button from "./ui/Button";

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  const [menuOpen, setMenuOpen] = useState(false);

  const isDashboard = pathname?.startsWith("/dashboard");

  return (
    <header className="w-full border-b bg-white sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.svg" alt="logo" className="w-8 h-8" />
          <span className="text-xl font-bold tracking-tight">ZeroVerify</span>
        </Link>

        {/* Desktop Menu */}
        <nav className="hidden md:flex items-center gap-8 text-sm font-medium">
          {!user && (
            <>
              <Link href="/pricing" className="hover:text-blue-600">
                Pricing
              </Link>

              <Link href="/docs/api" className="hover:text-blue-600">
                API Docs
              </Link>

              <Button
                variant="primary"
                onClick={() => router.push("/auth/send-otp")}
              >
                Login / Signup
              </Button>
            </>
          )}

          {user && (
            <>
              <Link
                className="hover:text-blue-600"
                href="/verification"
              >
                Verify Email
              </Link>

              <Link
                className="hover:text-blue-600"
                href="/bulk"
              >
                Bulk Jobs
              </Link>

              <Link
                className="hover:text-blue-600"
                href="/decision-maker"
              >
                Decision Maker
              </Link>

              <Link
                className="hover:text-blue-600"
                href="/api-keys"
              >
                API Keys
              </Link>

              <Link
                className="hover:text-blue-600"
                href="/billing"
              >
                Billing
              </Link>

              <Link
                className="hover:text-blue-600"
                href="/team"
              >
                Team
              </Link>

              <Button variant="secondary" onClick={logout}>
                Logout
              </Button>
            </>
          )}
        </nav>

        {/* Mobile Toggle */}
        <button
          className="md:hidden w-10 h-10 flex items-center justify-center"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <span className="text-2xl">☰</span>
        </button>
      </div>

      {/* Mobile Menu */}
      {menuOpen && (
        <div className="md:hidden border-t bg-white p-4 space-y-4">
          {!user && (
            <>
              <Link href="/pricing" className="block">
                Pricing
              </Link>
              <Link href="/docs/api" className="block">
                API Docs
              </Link>

              <Button
                variant="primary"
                className="w-full"
                onClick={() => router.push("/auth/send-otp")}
              >
                Login / Signup
              </Button>
            </>
          )}

          {user && (
            <>
              <Link href="/verification" className="block">
                Verify Email
              </Link>
              <Link href="/bulk" className="block">
                Bulk Jobs
              </Link>
              <Link href="/decision-maker" className="block">
                Decision Maker
              </Link>
              <Link href="/api-keys" className="block">
                API Keys
              </Link>
              <Link href="/billing" className="block">
                Billing
              </Link>
              <Link href="/team" className="block">
                Team
              </Link>

              <Button variant="secondary" className="w-full" onClick={logout}>
                Logout
              </Button>
            </>
          )}
        </div>
      )}
    </header>
  );
          }


"use client";

import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { Menu } from "lucide-react";

export default function NavBar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    router.push("/auth/send-otp");
  };

  return (
    <header className="h-14 bg-white border-b flex items-center justify-between px-4 lg:px-6 shadow-sm">
      {/* Mobile Sidebar Toggle */}
      <button
        className="lg:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-md"
        onClick={() => setOpen(true)}
      >
        <Menu size={22} />
      </button>

      {/* Title Placeholder - can be dynamic later */}
      <div className="font-medium text-gray-800 text-lg">Dashboard</div>

      {/* User Menu */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-600 hidden sm:block">
          {user?.email}
        </span>

        <button
          onClick={handleLogout}
          className="px-3 py-1.5 bg-gray-800 text-white rounded-md text-sm hover:bg-black"
        >
          Logout
        </button>
      </div>
    </header>
  );
}

"use client";

import { useAuth } from "@/hooks/useAuth";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function NavBar() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    logout();
    router.push("/auth/send-otp");
  };

  return (
    <header className="w-full bg-white shadow-sm h-16 flex items-center justify-between px-6 border-b">
      {/* Logo */}
      <div
        className="text-xl font-semibold cursor-pointer"
        onClick={() => router.push("/dashboard")}
      >
        ZeroVerify.ai
      </div>

      {/* Right side */}
      <div className="flex items-center gap-6">

        {/* Credits */}
        <div className="text-sm text-gray-600">
          Credits:{" "}
          <span className="text-blue-600 font-semibold">
            {user?.credits ?? 0}
          </span>
        </div>

        {/* Profile dropdown */}
        <div className="relative">
          <button
            onClick={() => setOpen(!open)}
            className="flex items-center gap-2 px-3 py-2 rounded hover:bg-gray-100 transition"
          >
            <div className="h-8 w-8 rounded-full bg-blue-600 text-white flex items-center justify-center">
              {user?.email?.[0]?.toUpperCase() || "U"}
            </div>
            <span className="text-sm text-gray-700">{user?.email}</span>
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-48 bg-white shadow-md rounded border z-50">
              <button
                onClick={() => router.push("/settings")}
                className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100"
              >
                Settings
              </button>

              <button
                onClick={() => router.push("/team")}
                className="w-full text-left px-4 py-2 text-sm hover:bg-gray-100"
              >
                Manage Team
              </button>

              <button
                onClick={handleLogout}
                className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
