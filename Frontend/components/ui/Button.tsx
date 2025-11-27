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
