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
