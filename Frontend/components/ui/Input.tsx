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
