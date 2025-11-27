export default function Loader() {
  return (
    <div className="flex items-center justify-center py-4">
      <div className="animate-spin h-6 w-6 border-2 border-black border-t-transparent rounded-full"></div>
    </div>
  );
}

"use client";

export default function Loader({ size = 20 }: { size?: number }) {
  return (
    <div
      className="animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
      style={{ width: size, height: size }}
    />
  );
}
"use client";

export default function Loader() {
  return (
    <div className="h-5 w-5 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin" />
  );
}
"use client";

export default function Loader() {
  return (
    <div className="h-4 w-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin" />
  );
}
