import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class WsHub:
    def __init__(self):
        self.connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, topics: set[str]):
        await websocket.accept()
        async with self._lock:
            self.connections[websocket] = topics

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.connections.pop(websocket, None)

    async def subscribe(self, websocket: WebSocket, topics: set[str]):
        async with self._lock:
            if websocket in self.connections:
                self.connections[websocket].update(topics)

    async def unsubscribe(self, websocket: WebSocket, topics: set[str]):
        async with self._lock:
            if websocket in self.connections:
                self.connections[websocket] -= topics

    async def broadcast(self, topic: str, payload: Any):
        msg = {
            "op": "publish",
            "topic": topic,
            "payload": payload,
            "ts": datetime.now().isoformat(),
        }
        data = json.dumps(msg)
        async with self._lock:
            dead = []
            for ws, topics in self.connections.items():
                if topic in topics:
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
            for ws in dead:
                self.connections.pop(ws, None)


hub = WsHub()


@router.websocket("/admin/ws")
async def websocket_endpoint(websocket: WebSocket):
    await hub.connect(websocket, set())

    try:
        while True:
            msg = await websocket.receive_json()
            op = msg.get("op")

            if op == "subscribe":
                topics = set(msg.get("topics", []))
                await hub.subscribe(websocket, topics)
            elif op == "unsubscribe":
                topics = set(msg.get("topics", []))
                await hub.unsubscribe(websocket, topics)
            elif op == "ping":
                await websocket.send_json({"op": "pong"})
    except WebSocketDisconnect:
        await hub.disconnect(websocket)
    except Exception:
        await hub.disconnect(websocket)


async def broadcast_topology_saved(topology_id: str):
    await hub.broadcast("topology.saved", {"topologyId": topology_id})


async def broadcast_group_progress(topology_id: str, group_id: str, payload: dict):
    await hub.broadcast("group.materialize.progress", {
        "topologyId": topology_id,
        "groupId": group_id,
        **payload,
    })
