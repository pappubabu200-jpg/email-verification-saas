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


"use client";

import { useState } from "react";
import { Briefcase, Mail, Building2, Globe, Phone, Info } from "lucide-react";
import { DecisionMakerResult } from "@/lib/api/decision_maker";

export default function DMDetailTabs({ dm }: { dm: DecisionMakerResult }) {
  const tabs = [
    { key: "overview", label: "Overview", icon: Info },
    { key: "contact", label: "Contact", icon: Phone },
    { key: "company", label: "Company", icon: Building2 },
    { key: "work", label: "Work History", icon: Briefcase },
  ];

  const [active, setActive] = useState("overview");

  return (
    <div className="mt-6">
      {/* TAB HEADER */}
      <div className="flex border-b gap-6">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className={`pb-2 flex items-center gap-2 ${
              active === t.key
                ? "border-b-2 border-blue-600 text-blue-600 font-semibold"
                : "text-gray-600 hover:text-blue-600"
            }`}
          >
            <t.icon size={16} />
            {t.label}
          </button>
        ))}
      </div>

      {/* TAB CONTENT */}
      <div className="mt-6">
        {active === "overview" && <OverviewTab dm={dm} />}
        {active === "contact" && <ContactTab dm={dm} />}
        {active === "company" && <CompanyTab dm={dm} />}
        {active === "work" && <WorkTab dm={dm} />}
      </div>
    </div>
  );
}

/* -------------------------
   TAB SECTIONS
-------------------------- */

function OverviewTab({ dm }: { dm: DecisionMakerResult }) {
  return (
    <div className="space-y-3 text-gray-700">
      <p><b>Name:</b> {dm.name}</p>
      <p><b>Title:</b> {dm.title || "—"}</p>
      <p><b>Company:</b> {dm.company || "—"}</p>

      {dm.confidence && (
        <p><b>Confidence Score:</b> {dm.confidence}%</p>
      )}

      {dm.location && (
        <p><b>Location:</b> {dm.location}</p>
      )}
    </div>
  );
}

function ContactTab({ dm }: { dm: DecisionMakerResult }) {
  return (
    <div className="space-y-3 text-gray-700">
      <p className="flex gap-2"><Mail size={16}/> <b>Email:</b> {dm.email || "—"}</p>
      <p><b>Phone:</b> {dm.phone || "—"}</p>
      <p><b>LinkedIn:</b> {dm.linkedin || "—"}</p>
      <p><b>Twitter:</b> {dm.twitter || "—"}</p>
      <p><b>Website:</b> {dm.website || "—"}</p>
    </div>
  );
}

function CompanyTab({ dm }: { dm: DecisionMakerResult }) {
  return (
    <div className="space-y-3 text-gray-700">
      <p><b>Company:</b> {dm.company || "—"}</p>
      <p><b>Industry:</b> {dm.industry || "—"}</p>
      <p><b>Company Size:</b> {dm.company_size || "—"}</p>
      <p><b>Website:</b> {dm.company_website || "—"}</p>
      <p><b>HQ:</b> {dm.company_location || "—"}</p>
    </div>
  );
}

function WorkTab({ dm }: { dm: DecisionMakerResult }) {
  if (!dm.work_history || dm.work_history.length === 0) {
    return <p>No work history available.</p>;
  }

  return (
    <div className="space-y-4">
      {dm.work_history.map((job, idx) => (
        <div key={idx} className="p-4 border rounded-xl bg-white">
          <p><b>Title:</b> {job.title}</p>
          <p><b>Company:</b> {job.company}</p>
          <p><b>Period:</b> {job.period || "—"}</p>
        </div>
      ))}
    </div>
  );
}


"use client";

import React from "react";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";

export default function DMResultsTable({
  items,
  page,
  total,
  onPage,
  onSelect,
}: {
  items: any[];
  page: number;
  total: number;
  onPage: (p: number) => void;
  onSelect: (item: any) => void;
}) {
  const totalPages = Math.max(1, Math.ceil((total || items.length) / 20));

  return (
    <Card className="p-0 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="p-3 text-left">Name</th>
            <th className="p-3 text-left">Title</th>
            <th className="p-3 text-left">Company</th>
            <th className="p-3 text-left">Email</th>
            <th className="p-3 text-left">Actions</th>
          </tr>
        </thead>

        <tbody>
          {items.map((it: any, idx: number) => (
            <tr key={idx} className="border-b hover:bg-gray-50">
              <td className="p-3">{it.name || "-"}</td>
              <td className="p-3">{it.title || "-"}</td>
              <td className="p-3">{it.company || "-"}</td>
              <td className="p-3">{it.email || "-"}</td>
              <td className="p-3">
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => onSelect(it)}>View</Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      // trigger enrichment
                      fetch("/decision-maker/enrich", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ id: it.id || it.email }),
                      }).then(() => {
                        // feedback maybe handled via WS
                      });
                    }}
                  >
                    Enrich
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* pagination */}
      <div className="p-3 flex items-center justify-between">
        <div className="text-xs text-gray-500">Showing page {page} / {totalPages}</div>
        <div className="flex gap-2">
          <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Prev</Button>
          <Button size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
        </div>
      </div>
    </Card>
  );
}

