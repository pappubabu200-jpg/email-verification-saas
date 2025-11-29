
import os
from datetime import datetime

TREE_FILE = "repo_tree.txt"
README_FILE = "README.md"


# Template for README
README_TEMPLATE = """
# 🚀 {project_name}
### Email Verification + Bulk Processing + Decision Maker Intelligence Platform  
*(ZeroBounce / Clearout / Snov.io level SaaS)*

---

## 📌 Overview

{project_name} is a full-scale verification and intelligence platform providing:

✔ Real-time email verification  
✔ Bulk CSV/ZIP verification (WebSocket Streaming)  
✔ Enterprise-grade scoring & risk algorithms  
✔ Decision Maker Finder (PDL + Apollo + AI pattern engine)  
✔ WebSocket fanout system (Redis PubSub → FastAPI → Frontend)  
✔ Admin metrics dashboard  
✔ Team Billing, Credit System, API Keys  
✔ Full FastAPI + Celery + Redis + MinIO stack  

Built for **high throughput**, **multi-worker scaling**, and **enterprise customers**.

---

## 🧠 Tech Stack

### **Backend**
- **FastAPI** (Async REST + WebSocket)
- **PostgreSQL / SQLAlchemy**
- **Redis (Pub/Sub)** – real-time fanout system  
- **Celery** – heavy background workers  
- **MinIO (S3 storage)** – store bulk outputs  
- **PDL + Apollo Clients** – decision maker enrichment  
- **JWT Authentication**
- **Webhook Engine** (events: bulk_completed, bulk_failed, verification_completed...)

### **Frontend**
- **Next.js 14 (App Router)**
- **React + TailwindCSS**
- **WebSocket Hooks** (useBulkWS, useVerificationWS, useAdminMetricsWS)
- **Recharts** – charts & analytics  
- **Components/UI folder** (Buttons, Cards, Tables, Modals, etc.)

---

## 🧩 Key Features

### 🔥 **Email Verification Engine**
- SMTP checks  
- DNS, MX, role-account detection  
- Disposable detection  
- Catch-all & risk scoring  
- Real-time WebSocket updates  

### 📁 **Bulk Processor**
- CSV + ZIP parsing  
- Multi-worker Celery processing  
- Each email verified individually  
- Progress → Redis → WS → UI  
- CSV & JSON outputs stored in MinIO  
- Auto credit deduction  

### 🧑‍💼 **Decision Maker Finder**
- PDL domain search  
- Apollo people search  
- Email pattern guessing  
- AI-powered enrichment pipeline  
- DM Live WebSocket task progress  

### 🧑‍⚖️ **Admin Dashboard**
- Real-time metrics (Redis live)  
- Verification load  
- Deliverability score  
- Recent activity  
- Billing usage  

---

## 📂 Repository Structure

Below is your latest **auto-generated** repo tree:
