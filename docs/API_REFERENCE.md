# 📡 API Reference – ZeroVerify AI

---

# 🔐 Auth APIs

### `POST /auth/send-otp`
### `POST /auth/verify-otp`
### `POST /auth/login`

---

# ✉ Verification APIs

### `GET /verification/single?email=`
### `POST /verification/bulk`

### WebSocket:

/ws/verification/{user_id}

---

# 📦 Bulk Job APIs

### `POST /bulk`
### `GET /bulk/{job_id}`

### WebSocket:

/ws/bulk/{job_id}

---

# 🧑‍💼 Decision Maker APIs

### `GET /decision-maker/search`
### `GET /decision-maker/{id}`
### `POST /decision-maker/{id}/enrich`

### WebSocket:

/ws/dm/{id}

---

# 🧑‍⚖️ Admin APIs

### WebSocket:

/ws/admin/metrics

---

# 🌐 Webhook Events

- `bulk_job.finished`
- `bulk_job.failed`
- `verification.completed`
- `dm.enriched`


---
