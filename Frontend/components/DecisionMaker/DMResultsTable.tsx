"use client";

import { useRouter } from "next/navigation";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";

export default function DMResultsTable({ results, page, total, onPageChange }: any) {
  const router = useRouter();

  const pages = Math.ceil(total / 20);

  return (
    <Card>
      <table className="w-full text-left">
        <thead>
          <tr className="border-b text-gray-600">
            <th className="p-3">Name</th>
            <th className="p-3">Title</th>
            <th className="p-3">Company</th>
            <th className="p-3">Domain</th>
            <th className="p-3">Seniority</th>
            <th className="p-3"></th>
          </tr>
        </thead>

        <tbody>
          {results.map((person: any) => (
            <tr key={person.id} className="border-b hover:bg-gray-50">
              <td className="p-3">{person.name}</td>
              <td className="p-3">{person.title}</td>
              <td className="p-3">{person.company}</td>
              <td className="p-3">{person.domain}</td>
              <td className="p-3">{person.seniority}</td>
              <td className="p-3">
                <Button
                  size="sm"
                  onClick={() => router.push(`/decision-maker/${person.id}`)}
                >
                  View
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex justify-center mt-6 gap-2">
          {Array.from({ length: pages }).map((_, i) => (
            <Button
              key={i}
              size="sm"
              variant={page === i + 1 ? "primary" : "outline"}
              onClick={() => onPageChange(i + 1)}
            >
              {i + 1}
            </Button>
          ))}
        </div>
      )}
    </Card>
  );
}
