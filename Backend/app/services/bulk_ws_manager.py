# Backend/app/services/bulk_ws_manager.py

# Note: The websocket object is expected to be a Starlette/FastAPI WebSocket instance,
# which provides the send_json method.

class BulkWSManager:
    """
    Manages active WebSocket connections for bulk job progress tracking.
    Connections are grouped by job_id.
    """
    def __init__(self):
        # Dictionary to hold active websockets: {job_id: [websocket1, websocket2, ...]}
        # We use a list to store multiple clients viewing the same job's progress.
        self.active: dict[int, list] = {}

    async def connect(self, job_id: int, websocket):
        """Accepts a connection and adds the websocket to the active list for the given job_id."""
        await websocket.accept()
        self.active.setdefault(job_id, [])
        self.active[job_id].append(websocket)

    def disconnect(self, job_id: int, websocket):
        """Removes a websocket from the active list for the given job_id."""
        if job_id in self.active:
            try:
                self.active[job_id].remove(websocket)
            except ValueError:
                # Ignore if the socket is already removed
                pass

    async def broadcast(self, job_id: int, message: dict):
        """
        Sends a JSON message to all active websockets connected to the specified job_id.
        Removes any websockets that fail to send (assuming they are dead).
        """
        sockets = self.active.get(job_id, [])
        dead = []
        # Iterate over a copy of the list for safe removal later
        for ws in list(sockets):
            try:
                # Attempt to send the JSON message
                await ws.send_json(message)
            except Exception:
                # Catch any disconnect/connection closed exception
                dead.append(ws)

        # Remove dead sockets from the list
        for d in dead:
            try:
                sockets.remove(d)
            except ValueError:
                pass # Ignore if the socket is already removed

# Global instance of the WebSocket Manager for singleton usage across the application
bulk_ws_manager = BulkWSManager()


async def broadcast_bulk_job_progress(job_id: int, processed: int, total: int, stats: dict = None):
    """
    A utility function to format and broadcast the 'progress' message for a bulk job.

    This function abstracts the message formatting and ensures the global manager is used.

    Args:
        job_id: The ID of the bulk job.
        processed: The number of items processed so far.
        total: The total number of items to process.
        stats: Optional dictionary containing additional processing statistics.
    """
    message = {
        "event": "progress",
        "processed": processed,
        "total": total,
        "stats": stats if stats is not None else {},
    }
    await bulk_ws_manager.broadcast(job_id, message)
