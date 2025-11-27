export default function ErrorBanner({ message }) {
  if (!message) return null;

  return (
    <div className="w-full bg-red-50 border border-red-200 text-red-700 p-3 rounded-md mb-3">
      {message}
    </div>
  );
}
"use client";

interface Props {
  message: string;
}

export default function ErrorBanner({ message }: Props) {
  if (!message) return null;

  return (
    <div className="w-full rounded-xl bg-red-50 border border-red-300 text-red-700 px-4 py-3 text-sm mb-4">
      <strong className="font-medium">Error: </strong> {message}
    </div>
  );
}
"use client";

interface Props {
  message: string;
}

export default function ErrorBanner({ message }: Props) {
  if (!message) return null;

  return (
    <div className="w-full rounded-xl bg-red-50 border border-red-300 text-red-700 px-4 py-3 text-sm mb-4">
      <strong className="font-medium">Error: </strong> {message}
    </div>
  );
}
