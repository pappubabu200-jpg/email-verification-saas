# 🎨 Frontend Architecture – ZeroVerify AI

Frontend built using **Next.js App Router**, fully real-time using WebSockets.

---

## ✨ Tech Stack

- **Next.js 14 (App Router)**
- **React**
- **TailwindCSS**
- **Recharts**
- **WebSocket hooks**
- **Axios client**
- **Modular UI Components**

---

## 🧱 Folder Structure

frontend/ app/ auth/ dashboard/ bulk/ decision-maker/ admin/ components/ ui/ charts/ ws/ hooks/ useBulkWS.ts useVerificationWS.ts useAdminMetricsWS.ts useDMEnrichmentWS.ts lib/ axios.ts

---

## 📦 Core UI Components

### `/components/ui`
- Button
- Input
- Card
- Loader
- ErrorBanner
- Modal
- Table

All design is **reusable**, **responsive**, **enterprise-grade**.

---

## 🔌 WebSocket Hooks

### 1. `useBulkWS(jobId)`
Live bulk job progress:
- processed
- total
- valid/invalid
- event: progress, completed, failed

### 2. `useVerificationWS(userId)`
Live:
- credits
- single verifications
- last 20 events

### 3. `useAdminMetricsWS()`
Live admin dashboard:
- deliverability score
- recent events
- load metrics

### 4. `useDMEnrichmentWS(dmId)`
Live decision maker enrichment:
- enrich_started
- progress step
- enrich_completed
- failed

---

## 🧠 Pages

### `/bulk/[jobId]`
Real-time bulk viewer.

### `/decision-maker/[id]`
DM enrichment live.

### `/admin/metrics`
Real-time admin dashboard.

### `/dashboard`
User dashboard + verification stream.

---

## 🎯 Summary

Frontend is:

- Real-time
- Modular
- Clean
- Optimized for enterprise SaaS
- Identical to ZeroBounce / Snov.io experiences
