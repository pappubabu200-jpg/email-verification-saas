export default function ErrorBanner({ message }) {
  if (!message) return null;

  return (
    <div className="w-full bg-red-50 border border-red-200 text-red-700 p-3 rounded-md mb-3">
      {message}
    </div>
  );
}
