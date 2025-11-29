# WebSockets & Redis PubSub

Explain:
- ws_broker
- Channels: bulk:{jobId}, user:{userId}:verification, admin:metrics, dm:{id}
- Flow: Celery → Redis → FastAPI WS → Browser
