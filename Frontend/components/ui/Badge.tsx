"use client";

import React from "react";

interface BadgeProps {
  children: React.ReactNode;
  variant?:
    | "success"
    | "danger"
    | "warning"
    | "info"
    | "neutral";
  size?: "sm" | "md";
  className?: string;
}

export default function Badge({
  children,
  variant = "neutral",
  size = "md",
  className = "",
}: BadgeProps) {
  const base =
    "inline-flex items-center font-medium rounded-full whitespace-nowrap";

  const sizeStyles = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-3 py-1",
  }[size];

  const colorStyles = {
    success: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
    danger: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
    warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300",
    info: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
    neutral: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300",
  }[variant];

  return (
    <span className={`${base} ${sizeStyles} ${colorStyles} ${className}`}>
      {children}
    </span>
  );
}

"use client";

import React from "react";
import clsx from "clsx";

type BadgeVariant =
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "neutral";

interface BadgeProps {
  text: string;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: "bg-green-100 text-green-700 border border-green-300",
  warning: "bg-yellow-100 text-yellow-700 border border-yellow-300",
  danger:  "bg-red-100 text-red-700 border border-red-300",
  info:    "bg-blue-100 text-blue-700 border border-blue-300",
  neutral: "bg-gray-100 text-gray-700 border border-gray-300",
};

export default function Badge({ text, variant = "neutral", className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "px-2 py-1 rounded-md text-xs font-medium",
        variantStyles[variant],
        className
      )}
    >
      {text}
    </span>
  );
        }


"use client";

import React from "react";
import clsx from "clsx";

interface BadgeProps {
  children: React.ReactNode;
  variant?: 
    | "success"
    | "danger"
    | "warning"
    | "info"
    | "neutral";
  className?: string;
}

export default function Badge({ children, variant = "neutral", className }: BadgeProps) {
  const variants: Record<string, string> = {
    success: "bg-green-100 text-green-700 border border-green-200",
    danger: "bg-red-100 text-red-700 border border-red-200",
    warning: "bg-yellow-100 text-yellow-700 border border-yellow-200",
    info: "bg-blue-100 text-blue-700 border border-blue-200",
    neutral: "bg-gray-100 text-gray-700 border border-gray-200",
  };

  return (
    <span
      className={clsx(
        "px-3 py-1 text-xs font-medium rounded-full whitespace-nowrap",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
