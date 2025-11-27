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
