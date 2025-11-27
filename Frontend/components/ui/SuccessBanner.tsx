
export default function SuccessBanner({ message }) {
  if (!message) return null;

  return (
    <div className="w-full bg-green-50 border border-green-200 text-green-700 p-3 rounded-md mb-3">
      {message}
    </div>
  );
}
