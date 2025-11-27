"use client";

import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";

export default function DMSearchForm({
  query,
  setQuery,
  role,
  setRole,
  seniority,
  setSeniority,
  companyDomain,
  setCompanyDomain,
  onSearch,
}: any) {
  return (
    <div className="p-6 bg-white rounded-lg shadow space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">

        <Input
          label="Company / Person Name"
          placeholder="Google, Microsoft or 'John Doe'"
          value={query}
          onChange={(e: any) => setQuery(e.target.value)}
        />

        <Input
          label="Company Domain"
          placeholder="google.com"
          value={companyDomain}
          onChange={(e: any) => setCompanyDomain(e.target.value)}
        />

        <Input
          label="Role / Department"
          placeholder="CEO, CTO, HR, Marketing"
          value={role}
          onChange={(e: any) => setRole(e.target.value)}
        />

        <Input
          label="Seniority"
          placeholder="C-Level, Director, VP"
          value={seniority}
          onChange={(e: any) => setSeniority(e.target.value)}
        />
      </div>

      <Button className="w-full" variant="primary" onClick={onSearch}>
        Search
      </Button>
    </div>
  );
}

"use client";

import { useState } from "react";
import Input from "@/components/ui/Input";
import Button from "@/components/ui/Button";
import axios from "@/lib/axios";

export default function DMSearchForm({
  initialQuery = "",
  onSearch,
  onQuickCompany,
}: {
  initialQuery?: string;
  onSearch: (q: string, company?: string) => void;
  onQuickCompany?: (company: string) => void;
}) {
  const [q, setQ] = useState(initialQuery);
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  const handleSearch = () => {
    onSearch(q.trim(), company.trim() || undefined);
  };

  const fetchCompanySuggestions = async (term: string) => {
    if (!term) return setSuggestions([]);
    try {
      const res = await axios.get("/decision-maker/company-suggest", { params: { q: term } });
      setSuggestions(res.data || []);
    } catch {
      setSuggestions([]);
    }
  };

  return (
    <div className="bg-white p-4 rounded shadow-sm mb-4">
      <div className="flex gap-3">
        <Input
          label="Name or Role (e.g. VP Marketing)"
          value={q}
          onChange={(e: any) => setQ(e.target.value)}
          placeholder="e.g. Head of Growth"
        />
        <div className="w-64">
          <Input
            label="Company (optional)"
            value={company}
            onChange={(e: any) => {
              setCompany(e.target.value);
              fetchCompanySuggestions(e.target.value);
            }}
            placeholder="Company name"
          />
          {suggestions.length > 0 && (
            <div className="mt-1 bg-white border rounded max-h-40 overflow-auto">
              {suggestions.map((s, i) => (
                <div
                  key={i}
                  className="p-2 hover:bg-gray-50 cursor-pointer text-sm"
                  onClick={() => {
                    setCompany(s);
                    setSuggestions([]);
                    onQuickCompany && onQuickCompany(s);
                  }}
                >
                  {s}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-end">
          <Button onClick={handleSearch} variant="primary">
            Search
          </Button>
        </div>
      </div>
    </div>
  );
}

