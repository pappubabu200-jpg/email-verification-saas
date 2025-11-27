"use client";

import { useEffect, useState } from "react";
import axios from "@/lib/axios";

import DMSearchForm from "@/components/DecisionMaker/DMSearchForm";
import DMResultsTable from "@/components/DecisionMaker/DMResultsTable";
import Loader from "@/components/ui/Loader";
import ErrorBanner from "@/components/ui/ErrorBanner";

export default function DecisionMakerPage() {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [seniority, setSeniority] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");

  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  // ------------------------------
  // Fetch decision makers
  // ------------------------------
  const fetchData = async (pageNumber = 1) => {
    if (!query) return;

    setLoading(true);
    setError(null);

    try {
      const res = await axios.get("/decision-maker/search", {
        params: {
          query,
          domain: companyDomain,
          role,
          seniority,
          page: pageNumber,
        },
      });

      setResults(res.data.results || []);
      setTotal(res.data.total || 0);
      setPage(pageNumber);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Search failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = () => fetchData(1);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      <h1 className="text-3xl font-semibold">Decision Maker Finder</h1>
      <p className="text-gray-600">
        Search key people (CEO, CTO, HR, Founder, etc.) of any company using Apollo + PDL enrichment.
      </p>

      {/* Search Form */}
      <DMSearchForm
        query={query}
        setQuery={setQuery}
        role={role}
        setRole={setRole}
        seniority={seniority}
        setSeniority={setSeniority}
        companyDomain={companyDomain}
        setCompanyDomain={setCompanyDomain}
        onSearch={handleSearch}
      />

      {/* Results */}
      {loading && (
        <div className="flex justify-center py-10">
          <Loader />
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {!loading && results.length > 0 && (
        <DMResultsTable
          results={results}
          page={page}
          total={total}
          onPageChange={(p: number) => fetchData(p)}
        />
      )}

      {!loading && results.length === 0 && query && !error && (
        <p className="text-gray-500">No results found. Try another company or role.</p>
      )}
    </div>
  );
}
