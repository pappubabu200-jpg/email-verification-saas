export default function Card({ children, className = "" }) {
  return (
    <div
      className={`bg-white shadow-sm rounded-xl p-6 border border-gray-100 ${className}`}
    >
      {children}
    </div>
  );
}
