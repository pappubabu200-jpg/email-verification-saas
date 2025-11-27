
export default function SuccessBanner({ message }) {
  if (!message) return null;

  return (
    <div className="w-full bg-green-50 border border-green-200 text-green-700 p-3 rounded-md mb-3">
      {message}
    </div>
  );
}
"use client";

interface Props {
  message: string;
}

export default function SuccessBanner({ message }: Props) {
  if (!message) return null;

  return (
    <div className="w-full rounded-xl bg-green-50 border border-green-300 text-green-700 px-4 py-3 text-sm mb-4">
      <strong className="font-medium">Success: </strong> {message}
    </div>
  );
}
