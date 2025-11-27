
class BulkWSManager:
    def __init__(self):
        self.active: dict[int, list] = {}

    async def connect(self, job_id: int, websocket):
        await websocket.accept()
        self.active.setdefault(job_id, [])
        self.active[job_id].append(websocket)

    def disconnect(self, job_id: int, websocket):
        if job_id in self.active:
            self.active[job_id].remove(websocket)

    async def broadcast(self, job_id: int, message: dict):
        sockets = self.active.get(job_id, [])
        dead = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except:
                dead.append(ws)
        for d in dead:
            sockets.remove(d)


bulk_ws_manager = BulkWSManager()
