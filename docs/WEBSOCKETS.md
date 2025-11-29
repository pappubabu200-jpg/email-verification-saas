🔌 Real-Time WebSocket System

ZeroVerify uses **Redis PubSub** to fanout real-time events.

Celery Worker → Redis → FastAPI WS → Client Hook

All streams use the centralized:

ws_broker.publish(channel, payload)

---

## 🎯 Supported Channels

### 1. Bulk Jobs

bulk:{job_id}

### 2. User Verification Stream

user:{user_id}:verification

### 3. Admin Metrics Stream

admin:metrics

### 4. Decision Maker Enrichment Stream

dm:{id}

---

## 🔄 Flow Example (Bulk Progress)

for each email: Celery worker → publish to redis WS server → receives & forwards Frontend → useBulkWS updates UI live

---

## 🛠 WebSocket Routers

- `/ws/bulk/{job_id}`
- `/ws/verification/{user_id}`
- `/ws/admin/metrics`
- `/ws/dm/{id}`

Each one:

1. Opens WebSocket  
2. Subscribes to Redis channel  
3. Forwards every message  

---

## ❤️ Summary

Your WS system is fully **horizontal scalable**, **non-blocking**, **PubSub-driven**, and **cloud-native**.
