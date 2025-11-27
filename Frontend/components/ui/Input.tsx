"use client";
import React from "react";

export default function Input({
  label,
  type = "text",
  value,
  onChange,
  placeholder,
  error,
}) {
  return (
    <div className="flex flex-col gap-1 w-full">
      {label && <label className="text-sm font-medium text-gray-700">{label}</label>}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full px-4 py-2 border border-gray-300 rounded-md
                   focus:ring-2 focus:ring-black focus:border-black
                   transition-all duration-200"
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

"use client";

import React from "react";
import clsx from "clsx";

/**
 * Reusable Input component with:
 *  - label
 *  - error message
 *  - variants: default, small, large
 *  - full-width by default
 */

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | null;
  size?: "sm" | "md" | "lg";
}

export default function Input({
  label,
  error,
  size = "md",
  className,
  ...rest
}: InputProps) {
  const sizeStyles = {
    sm: "px-3 py-1 text-sm",
    md: "px-4 py-2 text-base",
    lg: "px-5 py-3 text-lg",
  };

  return (
    <div className="w-full">
      {label && (
        <label className="block mb-1 text-sm font-medium text-gray-700">
          {label}
        </label>
      )}

      <input
        {...rest}
        className={clsx(
          "w-full border rounded-xl bg-white focus:outline-none focus:ring-2 transition",
          error
            ? "border-red-500 focus:ring-red-400"
            : "border-gray-300 focus:ring-blue-500",
          sizeStyles[size],
          className
        )}
      />

      {error && (
        <p className="text-sm text-red-600 mt-1">
          {error}
        </p>
      )}
    </div>
  );
      }
"use client";

import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export default function Input({ label, error, ...props }: InputProps) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {label}
        </label>
      )}

      <input
        {...props}
        className={`
          w-full px-3 py-2 border rounded-lg text-sm outline-none transition
          ${error ? "border-red-500" : "border-gray-300"}
          focus:ring-2 focus:ring-blue-500 focus:border-blue-500
        `}
      />

      {error && (
        <p className="text-red-500 text-xs mt-1">{error}</p>
      )}
    </div>
  );
}


