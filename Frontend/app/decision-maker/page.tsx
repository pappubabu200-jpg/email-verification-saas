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

"use client";

import { useState, useEffect } from "react";
import DMSearchForm from "@/components/DecisionMaker/DMSearchForm";
import DMResultsTable from "@/components/DecisionMaker/DMResultsTable";
import DMResultCard from "@/components/DecisionMaker/DMResultCard";
import useDMStream from "@/hooks/useDMStream";
import axios from "@/lib/axios";
import Card from "@/components/ui/Card";
import Loader from "@/components/ui/Loader";

export default function DecisionMakerPage() {
  const [query, setQuery] = useState("");
  const [company, setCompany] = useState<string | null>(null);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  // Live stream for enrichment / background extractor events
  const dmStream = useDMStream();

  // Merge incoming live updates into existing results (match by id or email)
  useEffect(() => {
    if (!dmStream?.updates?.length) return;
    setResults((prev) => {
      const byId = new Map(prev.map((r) => [r.id || r.email, r]));
      dmStream.updates.forEach((u: any) => {
        const key = u.id || u.email;
        const existing = byId.get(key);
        if (existing) {
          byId.set(key, { ...existing, ...u });
        } else {
          byId.set(key, u);
        }
      });
      return Array.from(byId.values());
    });
  }, [dmStream?.updates]);

  const search = async (opts?: { q?: string; company?: string; page?: number }) => {
    setLoading(true);
    try {
      const params: any = {
        q: opts?.q ?? query,
        company: opts?.company ?? company,
        page: opts?.page ?? page,
        per_page: 20,
      };
      const res = await axios.get("/decision-maker/search", { params });
      setResults(res.data.results || []);
      setTotal(res.data.total || 0);
      setPage(res.data.page || 1);
    } catch (err: any) {
      console.error("DM search failed", err);
      // show toast / error handling as needed
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // initial search empty to show suggestions
    search({ q: "", page: 1 });
  }, []);

  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Decision Maker Finder</h1>
        <p className="text-sm text-gray-500">Find key decision makers, enrich with PDL & Apollo data.</p>
      </div>

      <DMSearchForm
        initialQuery={query}
        onSearch={(q, companyFilter) => {
          setQuery(q);
          setCompany(companyFilter || null);
          search({ q, company: companyFilter, page: 1 });
        }}
        onQuickCompany={(c) => {
          setCompany(c);
          search({ q: query, company: c, page: 1 });
        }}
      />

      {loading ? (
        <div className="p-8 flex justify-center"><Loader /></div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <DMResultsTable
              items={results}
              page={page}
              total={total}
              onPage={(p) => {
                setPage(p);
                search({ q: query, company, page: p });
              }}
              onSelect={(item) => setSelected(item)}
            />
          </div>

          <aside>
            <Card className="p-4">
              <h3 className="text-sm font-semibold mb-2">Live Enrichment</h3>
              <p className="text-xs text-gray-500 mb-3">
                Enrichment runs (PDL / Apollo) stream here. Click a result for detailed contact card.
              </p>

              {/* show last few live events */}
              <div className="space-y-2">
                {dmStream.updates.slice(-5).reverse().map((u: any, idx: number) => (
                  <div key={idx} className="p-2 border rounded bg-white">
                    <div className="text-xs text-gray-600">{u.source || "enr"}</div>
                    <div className="font-medium text-sm">{u.name || u.email || u.job_id}</div>
                    <div className="text-xs text-gray-500">{u.status || u.title || ""}</div>
                  </div>
                ))}
                {dmStream.updates.length === 0 && <div className="text-xs text-gray-400">No live enrichments yet</div>}
              </div>
            </Card>

            <div className="mt-4">
              <Card className="p-4">
                <h4 className="text-sm font-semibold mb-2">Quick Actions</h4>
                <button
                  className="w-full bg-blue-600 text-white p-2 rounded"
                  onClick={() => {
                    // trigger bulk DM extraction (example)
                    axios.post("/decision-maker/extract", { query, company });
                  }}
                >
                  Run Company Enrich
                </button>
              </Card>
            </div>
          </aside>
        </div>
      )}

      {/* Drawer / modal for selected result */}
      {selected && (
        <DMResultCard item={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import axios from "@/lib/axios";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import ErrorBanner from "@/components/ui/ErrorBanner";
import Loader from "@/components/ui/Loader";

export default function DecisionMakerStartPage() {
  const router = useRouter();

  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isValidDomain = (d: string) =>
    /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(d);

  const startDiscovery = async () => {
    setError(null);

    const cleaned = domain.trim().toLowerCase();
    if (!isValidDomain(cleaned)) {
      setError("Enter a valid company domain, e.g., stripe.com");
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post("/decision-maker/discover", {
        domain: cleaned,
      });

      const jobId = res.data?.job_id;
      if (!jobId) throw new Error("Invalid job response");

      // redirect to live discovery page
      router.push(`/decision-maker/live/${jobId}`);
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          "Failed to start discovery — try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 p-6">
      <div className="max-w-lg w-full space-y-6 p-8 bg-white rounded shadow">
        <h1 className="text-3xl font-semibold">Decision Maker Finder</h1>
        <p className="text-gray-600 text-sm">
          Enter a company domain to discover verified executives (CEO, CTO, CMO,
          etc.) using Apollo + PDL + AI guessing + verification engine.
        </p>

        {error && <ErrorBanner message={error} />}

        <Input
          label="Company Domain"
          placeholder="example.com"
          value={domain}
          onChange={(e: any) => setDomain(e.target.value)}
        />

        <Button
          variant="primary"
          className="w-full"
          disabled={loading}
          onClick={startDiscovery}
        >
          {loading ? (
            <div className="flex items-center gap-2">
              <Loader /> Starting…
            </div>
          ) : (
            "Start Discovery"
          )}
        </Button>
      </div>
    </div>
  );
        }


