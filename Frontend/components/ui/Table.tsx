"use client";

import React from "react";

interface Column<T> {
  key: keyof T | string;
  label: string;
  render?: (row: T) => React.ReactNode;
  width?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
}

export default function Table<T>({
  columns,
  data,
  loading = false,
  emptyMessage = "No data found",
  onRowClick,
}: TableProps<T>) {
  return (
    <div className="overflow-x-auto border rounded-xl bg-white dark:bg-neutral-900 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-neutral-700">
        {/* Header */}
        <thead>
          <tr className="bg-gray-50 dark:bg-neutral-800">
            {columns.map((col) => (
              <th
                key={String(col.key)}
                className={`px-4 py-3 text-left text-sm font-semibold text-gray-600 dark:text-gray-300 ${
                  col.width || ""
                }`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>

        {/* Body */}
        <tbody className="divide-y divide-gray-200 dark:divide-neutral-800">
          {/* Loading State */}
          {loading && (
            <tr>
              <td
                colSpan={columns.length}
                className="py-10 text-center text-gray-400"
              >
                Loading...
              </td>
            </tr>
          )}

          {/* Empty State */}
          {!loading && data.length === 0 && (
            <tr>
              <td
                colSpan={columns.length}
                className="py-10 text-center text-gray-400"
              >
                {emptyMessage}
              </td>
            </tr>
          )}

          {/* Rows */}
          {!loading &&
            data.map((row, i) => (
              <tr
                key={i}
                className={`hover:bg-gray-50 dark:hover:bg-neutral-800 ${
                  onRowClick ? "cursor-pointer" : ""
                }`}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td
                    key={String(col.key)}
                    className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300"
                  >
                    {col.render ? col.render(row) : (row as any)[col.key]}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
