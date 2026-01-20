"""WebSocket routes for real-time updates."""

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)

router = APIRouter()

# Connection manager for WebSocket clients
class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        """Accept and store a new connection."""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info("WebSocket connected", project_id=project_id)

    def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        """Remove a connection."""
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info("WebSocket disconnected", project_id=project_id)

    async def send_to_project(self, project_id: str, message: dict) -> None:
        """Send message to all connections for a project."""
        if project_id in self.active_connections:
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error("Failed to send WebSocket message", error=str(e))

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connections."""
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/research/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time research updates.

    Clients connect to receive updates about workflow progress.
    """
    await manager.connect(websocket, project_id)

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "project_id": project_id,
            "message": "Connected to research updates",
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0,
                )

                # Handle different message types
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    # Client wants to subscribe to specific events
                    events = data.get("events", [])
                    await websocket.send_json({
                        "type": "subscribed",
                        "events": events,
                    })

                elif msg_type == "feedback":
                    # Client sending feedback
                    await websocket.send_json({
                        "type": "feedback_received",
                        "data": data.get("data"),
                    })

            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
    except Exception as e:
        logger.error("WebSocket error", project_id=project_id, error=str(e))
        manager.disconnect(websocket, project_id)


async def send_progress_update(
    project_id: str,
    phase: str,
    agent: str,
    progress: float,
    message: str,
    data: dict | None = None,
) -> None:
    """Send a progress update to connected clients.

    Args:
        project_id: Project identifier.
        phase: Current workflow phase.
        agent: Agent name.
        progress: Progress percentage (0-100).
        message: Status message.
        data: Additional data to include.
    """
    await manager.send_to_project(project_id, {
        "type": "progress",
        "phase": phase,
        "agent": agent,
        "progress": progress,
        "message": message,
        "data": data or {},
    })


async def send_agent_output(
    project_id: str,
    agent: str,
    output: Any,
) -> None:
    """Send agent output to connected clients.

    Args:
        project_id: Project identifier.
        agent: Agent name.
        output: Agent output data.
    """
    await manager.send_to_project(project_id, {
        "type": "agent_output",
        "agent": agent,
        "output": output,
    })


async def send_phase_complete(
    project_id: str,
    phase: str,
    next_phase: str,
) -> None:
    """Notify clients that a phase is complete.

    Args:
        project_id: Project identifier.
        phase: Completed phase.
        next_phase: Next phase to execute.
    """
    await manager.send_to_project(project_id, {
        "type": "phase_complete",
        "phase": phase,
        "next_phase": next_phase,
    })


async def send_error(
    project_id: str,
    error: str,
    phase: str | None = None,
) -> None:
    """Send error notification to clients.

    Args:
        project_id: Project identifier.
        error: Error message.
        phase: Phase where error occurred.
    """
    await manager.send_to_project(project_id, {
        "type": "error",
        "error": error,
        "phase": phase,
    })


async def request_human_review(
    project_id: str,
    content: dict,
    options: list[str],
) -> None:
    """Request human review from connected clients.

    Args:
        project_id: Project identifier.
        content: Content to review.
        options: Available options for review.
    """
    await manager.send_to_project(project_id, {
        "type": "review_request",
        "content": content,
        "options": options,
    })
