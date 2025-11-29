# 🧵 Celery Worker System

Folder:

backend/app/tasks/ backend/app/workers/ backend/app/services/bulk_processor.py

---

## 🔥 Workers

### 1. Bulk Job Processor
- CSV/ZIP parsing  
- Email dedupe  
- Verify each email  
- WebSocket progress publish  
- Store CSV/JSON  
- Credit deduction  
- Webhook triggers  

### 2. Decision Maker Enrichment Worker
- PDL fetch  
- Apollo enrich  
- Email guess engine  
- Confidence scoring  
- DM WebSocket events  
- DB write  

### 3. Webhook Worker
Trigger webhooks without blocking FastAPI.

---

## ⏳ Scaling

Run multiple workers:

celery -A backend.app.celery_app worker -l info -Q default celery -A backend.app.celery_app worker -l info -Q enrichment

---

## 🎯 Summary

Workers run **100% async**, **distributed**, **non-blocking**, scalable to millions of emails/day.

