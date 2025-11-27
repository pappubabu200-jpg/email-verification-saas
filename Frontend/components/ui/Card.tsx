export default function Card({ children, className = "" }) {
  return (
    <div
      className={`bg-white shadow-sm rounded-xl p-6 border border-gray-100 ${className}`}
    >
      {children}
    </div>
  );
}

"use client";

import React from "react";

interface CardProps {
  title?: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export default function Card({
  title,
  description,
  children,
  footer,
  className = "",
}: CardProps) {
  return (
    <div
      className={`bg-white dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 
      rounded-2xl shadow-sm hover:shadow-md transition-all p-5 ${className}`}
    >
      {(title || description) && (
        <header className="mb-4">
          {title && (
            <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
              {title}
            </h2>
          )}
          {description && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {description}
            </p>
          )}
        </header>
      )}

      <div>{children}</div>

      {footer && <footer className="mt-4 pt-4 border-t">{footer}</footer>}
    </div>
  );
      }


"use client";

import React from "react";

interface CardProps {
  title?: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  padding?: string;
}

export default function Card({
  title,
  actions,
  children,
  footer,
  padding = "p-5",
}: CardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-all">
      {/* Header */}
      {(title || actions) && (
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}

      {/* Body */}
      <div className={padding}>{children}</div>

      {/* Footer */}
      {footer && (
        <div className="px-5 py-3 border-t border-gray-100 bg-gray-50 rounded-b-xl">
          {footer}
        </div>
      )}
    </div>
  );
}
