# 🏗 Backend Architecture – ZeroVerify AI

This document explains the backend structure powering:

- Real-time verification
- Bulk job pipeline
- Decision maker enrichment
- Team billing & credit engine
- Webhook events
- Redis fanout architecture

---

## ⚙ Tech Stack

- **FastAPI (Async)**
- **Celery Workers**
- **Redis (Pub/Sub)**
- **PostgreSQL + SQLAlchemy**
- **MinIO (S3 compatible)**
- **aioredis WebSocket broker**
- **JWT authentication**
- **PDL & Apollo external providers**

---

## 📚 Backend Directory Structure

backend/ app/ main.py db.py models/ routers/ services/ tasks/ workers/ utils/

---

## 🧩 Core Modules

### 1. **Routers**
Located in `backend/app/routers/`

| Router | Description |
|-------|-------------|
| `auth.py` | OTP Login, JWT, register |
| `verification.py` | Single + bulk verification API |
| `decision_maker.py` | Finder + enrichment + search |
| `admin.py` | Metrics, analytics, admin WS |
| `ws/*.py` | WebSocket endpoints |

---

## 🧠 Verification Engine

Path:

backend/app/services/verification_engine.py

Features:

- DNS/MX lookup  
- SMTP handshake  
- Role email detection  
- Disposable domain detection  
- Catch-all detection  
- Risk scoring  
- Full debug trace  

---

## 📦 Bulk Processor

Path:

backend/app/services/bulk_processor.py

Capabilities:

- Parse CSV/ZIP
- Deduplicate emails
- Verify one-by-one
- Publish progress → Redis
- Save CSV + JSON to MinIO
- Update DB rows

---

## 🔄 Real-time Streaming Pipeline

Celery Worker → Redis PubSub → FastAPI WS → Browser UI

This allows infinite scaling with multiple:

- workers  
- API servers  
- WS servers  
- clients  

---

## 🧑‍💼 Decision Maker Service

Path:

backend/app/services/decision_maker_service.py

Includes:

- PDL domain search  
- Apollo people search  
- Email pattern engine  
- Guessing (first.last, f.last…)  
- Enrichment worker  
- DM WebSocket events  

---

## 🔔 Webhooks

Path:

backend/app/services/webhook_service.py

Events:

- `bulk_job.finished`
- `bulk_job.failed`
- `verification.completed`
- `dm.enriched` (optional)

---

## 🔥 Summary

Your backend is **enterprise-level**, **distributed**, and **production-ready**—similar to ZeroBounce, Clearout, and Snov.io architecture.

FastAPI + Celery + Redis + MinIO + PostgreSQL = fully scalable SaaS backend
