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

"use client";

import React from "react";

interface Column {
  key: string;
  label: string;
  className?: string;
  render?: (item: any) => React.ReactNode;
}

interface TableProps {
  columns: Column[];
  data: any[];
  loading?: boolean;
  emptyMessage?: string;
  onRowClick?: (item: any) => void;
  className?: string;
}

export default function Table({
  columns,
  data,
  loading = false,
  emptyMessage = "No data available",
  onRowClick,
  className = "",
}: TableProps) {
  return (
    <div className={`overflow-x-auto border rounded-lg bg-white shadow-sm ${className}`}>
      <table className="w-full text-left border-collapse">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 text-sm font-semibold text-gray-600 border-b ${col.className || ""}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {loading ? (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center py-8 text-gray-500 text-sm"
              >
                Loading...
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center py-8 text-gray-500 text-sm"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item, idx) => (
              <tr
                key={idx}
                onClick={() => onRowClick && onRowClick(item)}
                className={`border-b hover:bg-gray-50 transition cursor-${
                  onRowClick ? "pointer" : "default"
                }`}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 text-sm text-gray-700">
                    {col.render ? col.render(item) : item[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
                                                        }
"use client";

import React from "react";
import clsx from "clsx";

export interface Column<T> {
  key: string;
  label: string;
  className?: string;
  render?: (row: T) => React.ReactNode;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  onRowClick?: (row: T) => void;
  emptyText?: string;
}

export default function Table<T>({
  columns,
  data,
  onRowClick,
  emptyText = "No records found.",
}: TableProps<T>) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-100 text-gray-700 border-b">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx("px-4 py-3 font-semibold text-left", col.className)}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center py-6 text-gray-500"
              >
                {emptyText}
              </td>
            </tr>
          ) : (
            data.map((row: any, idx: number) => (
              <tr
                key={idx}
                onClick={() => onRowClick?.(row)}
                className={clsx(
                  "border-b hover:bg-gray-50 transition cursor-pointer",
                  idx % 2 === 0 ? "bg-white" : "bg-gray-50"
                )}
              >
                {columns.map((col) => (
                  <td key={col.key} className={clsx("px-4 py-3", col.className)}>
                    {col.render ? col.render(row) : String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
                }


