"use client";
import clsx from "clsx";

export default function Button({
  children,
  onClick,
  type = "button",
  variant = "primary",
  disabled = false,
  className = "",
}) {
  const base =
    "px-4 py-2 rounded-md font-medium transition-all duration-200 flex items-center justify-center";

  const variants = {
    primary:
      "bg-black text-white hover:bg-gray-900 active:scale-95 disabled:bg-gray-400",
    secondary:
      "bg-white border border-gray-300 text-gray-900 hover:bg-gray-50 active:scale-95",
    danger:
      "bg-red-600 text-white hover:bg-red-500 active:scale-95 disabled:bg-red-300",
  };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(base, variants[variant], className)}
    >
      {children}
    </button>
  );
}


"use client";

import React, { ButtonHTMLAttributes, PropsWithChildren } from "react";
import clsx from "clsx";

/**
 * Button primitive used across the app.
 *
 * Props:
 *  - variant: "primary" | "secondary" | "ghost" | "danger"
 *  - size: "sm" | "md" | "lg"
 *  - fullWidth: boolean -> stretch to container width
 *  - loading: boolean -> disables button and shows subtle spinner
 *
 * Usage:
 *  <Button variant="primary" onClick={...}>Send OTP</Button>
 */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  loading?: boolean;
  asChild?: boolean; // reserved for future slot usage
}

const base = "inline-flex items-center justify-center rounded-2xl font-medium transition focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  primary: "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500",
  secondary: "bg-white border border-gray-200 text-gray-800 hover:bg-gray-50 focus:ring-gray-300",
  ghost: "bg-transparent text-gray-800 hover:bg-gray-100 focus:ring-gray-200",
  danger: "bg-red-600 text-white hover:bg-red-700 focus:ring-red-500",
};

const sizes: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-3 text-base",
};

export default function Button({
  children,
  variant = "primary",
  size = "md",
  fullWidth = false,
  loading = false,
  className,
  ...rest
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      {...rest}
      className={clsx(
        base,
        variants[variant],
        sizes[size],
        fullWidth ? "w-full" : "inline-block",
        className
      )}
      disabled={loading || rest.disabled}
      aria-busy={loading ? true : undefined}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <svg
            className="animate-spin h-4 w-4 text-white"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
            />
          </svg>
          <span className="sr-only">Loading</span>
          <span>{children}</span>
        </span>
      ) : (
        children
      )}
    </button>
  );
      }
