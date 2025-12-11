"""Rotas WebSocket para notificações em tempo real."""
from fastapi import WebSocket, WebSocketDisconnect

from app.websocket.manager import websocket_manager


async def websocket_endpoint(websocket: WebSocket, request_id: str | None = None):
    """Endpoint WebSocket para notificações em tempo real."""
    await websocket_manager.connect(websocket, request_id)
    try:
        while True:
            # Mantém conexão viva e escuta mensagens do cliente (se necessário)
            data = await websocket.receive_text()
            # Por enquanto, apenas mantém conexão viva
            # Cliente pode enviar ping para manter conexão
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


async def websocket_endpoint_with_id(websocket: WebSocket, request_id: str):
    """Endpoint WebSocket para um request_id específico."""
    await websocket_manager.connect(websocket, request_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)

