"""Gerenciador de conexões WebSocket para notificações em tempo real."""
from typing import Dict, Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Gerencia conexões WebSocket e envia notificações."""

    def __init__(self):
        # Armazena conexões por request_id
        self._connections_by_request: Dict[str, Set[WebSocket]] = {}
        # Armazena todas as conexões (para broadcast)
        self._all_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, request_id: str | None = None):
        """Aceita uma nova conexão WebSocket."""
        await websocket.accept()
        self._all_connections.add(websocket)

        if request_id:
            if request_id not in self._connections_by_request:
                self._connections_by_request[request_id] = set()
            self._connections_by_request[request_id].add(websocket)
            logger.info(f"Cliente conectado para request_id: {request_id}")

    def disconnect(self, websocket: WebSocket):
        """Remove uma conexão WebSocket."""
        self._all_connections.discard(websocket)

        # Remove de todas as conexões por request_id
        for request_id, connections in list(self._connections_by_request.items()):
            connections.discard(websocket)
            if not connections:
                del self._connections_by_request[request_id]

    async def send_to_request(self, request_id: str, message: dict):
        """Envia mensagem para todas as conexões de um request_id específico."""
        if request_id not in self._connections_by_request:
            logger.debug(f"Nenhuma conexão ativa para request_id: {request_id}")
            return

        disconnected = set()
        for websocket in list(self._connections_by_request[request_id]):
            try:
                # Verifica se a conexão ainda está ativa
                if websocket.client_state.name != "CONNECTED":
                    disconnected.add(websocket)
                    continue
                await websocket.send_json(message)
            except Exception as e:
                # Só loga se não for uma desconexão esperada
                error_msg = str(e).lower()
                if "connection closed" not in error_msg and "disconnect" not in error_msg:
                    logger.warning(f"Erro ao enviar mensagem para WebSocket: {e}")
                disconnected.add(websocket)

        # Remove conexões desconectadas
        for ws in disconnected:
            self.disconnect(ws)

    async def broadcast(self, message: dict):
        """Envia mensagem para todas as conexões ativas."""
        if not self._all_connections:
            return  # Não há conexões, não precisa fazer nada

        disconnected = set()
        for websocket in list(self._all_connections):
            try:
                # Verifica se a conexão ainda está ativa
                if websocket.client_state.name != "CONNECTED":
                    disconnected.add(websocket)
                    continue
                await websocket.send_json(message)
            except Exception as e:
                # Só loga se não for uma desconexão esperada
                error_msg = str(e).lower()
                if "connection closed" not in error_msg and "disconnect" not in error_msg:
                    logger.warning(f"Erro ao fazer broadcast para WebSocket: {e}")
                disconnected.add(websocket)

        # Remove conexões desconectadas
        for ws in disconnected:
            self.disconnect(ws)

    async def notify_status_update(self, request_id: str, status: str, message: str = "", progress: int = 0):
        """Envia notificação de atualização de status."""
        notification = {
            "type": "status_update",
            "request_id": request_id,
            "status": status,
            "message": message,
            "progress": progress,
        }
        await self.send_to_request(request_id, notification)
        # Também faz broadcast para atualizar histórico em tempo real
        await self.broadcast({
            "type": "history_update",
            "request_id": request_id,
            "status": status,
        })


# Instância global do gerenciador
websocket_manager = WebSocketManager()

