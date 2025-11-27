import axios from "../axios";

// ---------------------------------------------
// Types
// ---------------------------------------------
export interface DMSearchParams {
  name?: string;
  company?: string;
  domain?: string;
  title?: string;
  limit?: number;
}

export interface DecisionMakerResult {
  id: string | number;
  name: string;
  title?: string;
  email?: string;
  company?: string;
  company_domain?: string;
  confidence?: number;
  linkedin?: string;
}

export interface DecisionMakerProfile {
  profile: {
    id: string | number;
    name: string;
    title?: string;
    seniority?: string;
    department?: string;
    email?: string;
    phone?: string;

    linkedin?: string;
    twitter?: string;
    github?: string;

    experience?: {
      company: string;
      title: string;
      start: string;
      end?: string | null;
    }[];
  };

  company: {
    id?: string | number;
    name?: string;
    domain?: string;
    size?: string;
    industry?: string;
    location?: string;
  };
}

// ---------------------------------------------
// API METHODS
// ---------------------------------------------

// Search decision makers
export async function searchDecisionMakers(
  params: DMSearchParams
): Promise<DecisionMakerResult[]> {
  const res = await axios.get("/decision-maker/search", { params });
  return res.data.results || [];
}

// Get detail for one decision maker
export async function getDecisionMakerById(
  id: string | number
): Promise<DecisionMakerProfile> {
  const res = await axios.get(`/decision-maker/${id}`);
  return res.data;
}

// Save as CRM contact (optional future feature)
export async function saveDecisionMakerToCRM(payload: {
  id: string | number;
  notes?: string;
  tags?: string[];
}) {
  const res = await axios.post("/decision-maker/save", payload);
  return res.data;
}

// Export as CSV (optional future feature)
export async function exportDecisionMakerCSV(id: string | number) {
  const res = await axios.get(`/decision-maker/${id}/export/csv`, {
    responseType: "blob",
  });
  return res.data;
}

// Export vCard (optional future feature)
export async function exportDecisionMakerVCard(id: string | number) {
  const res = await axios.get(`/decision-maker/${id}/export/vcard`, {
    responseType: "blob",
  });
  return res.data;
}

// Frontend/lib/api/decision_maker.ts
import axios from "../axios";

export type DMResult = {
  id: string;
  name?: string;
  title?: string;
  company?: string;
  email?: string;
  confidence?: number;
  linkedin?: string;
  // other fields...
};

export async function searchDecisionMakers(q: string, limit = 10) {
  const res = await axios.get("/decision-maker/search", { params: { q, limit } });
  return res.data.results as DMResult[];
}

export async function getDecisionMakerDetail(uid: string) {
  const res = await axios.get(`/decision-maker/${encodeURIComponent(uid)}`);
  return res.data as any;
}
import axios from "@/lib/axios";

export const searchDM = (params: any) => axios.get("/decision-maker/search", { params });
export const enrichDM = (idOrEmail: string) => axios.post("/decision-maker/enrich", { id: idOrEmail });
export const getDM = (id: string) => axios.get(`/decision-maker/${id}`);
export const companySuggest = (q: string) => axios.get("/decision-maker/company-suggest", { params: { q }});
