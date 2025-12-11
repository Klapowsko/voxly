"""Sistema de rastreamento de status para requisições."""
import asyncio
import logging
import queue
from typing import Dict, Optional, Tuple
from datetime import datetime

# Armazena status em memória (em produção, usar Redis ou similar)
_status_store: Dict[str, Dict] = {}

# Fila thread-safe para atualizações de status de contextos síncronos
_status_queue: queue.Queue[Tuple[str, str, int, str]] = queue.Queue()

# Referência ao loop principal para envio de atualizações
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_processing_task: Optional[asyncio.Task] = None

logger = logging.getLogger(__name__)


def set_status(request_id: str, stage: str, progress: int, message: str = ""):
    """Define o status de uma requisição."""
    _status_store[request_id] = {
        "stage": stage,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now().isoformat(),
    }


def get_status(request_id: str) -> Optional[Dict]:
    """Obtém o status de uma requisição."""
    return _status_store.get(request_id)


def clear_status(request_id: str):
    """Remove o status de uma requisição."""
    _status_store.pop(request_id, None)


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Define o loop principal para envio de atualizações de status."""
    global _main_loop, _processing_task
    _main_loop = loop
    # Inicia task de processamento da fila se ainda não estiver rodando
    if _processing_task is None or _processing_task.done():
        _processing_task = loop.create_task(_process_status_queue())


async def _process_status_queue() -> None:
    """Processa a fila de atualizações de status e envia via WebSocket."""
    from app.websocket.manager import websocket_manager
    
    def _get_from_queue():
        """Função auxiliar para pegar item da fila em thread."""
        try:
            return _status_queue.get(timeout=0.1)
        except queue.Empty:
            return None
    
    while True:
        try:
            # Pega item da fila usando thread para não bloquear o loop
            item = await asyncio.to_thread(_get_from_queue)
            if item is None:
                await asyncio.sleep(0.05)  # Sleep menor quando fila vazia
                continue
            
            request_id, stage, progress, message = item
            
            # Envia via WebSocket
            try:
                await websocket_manager.notify_status_update(request_id, stage, message, progress)
            except Exception as e:
                logger.debug(f"Erro ao enviar status via WebSocket para {request_id}: {e}")
        except Exception as e:
            logger.error(f"Erro ao processar fila de status: {e}", exc_info=True)
            await asyncio.sleep(0.1)


def notify_status_from_thread(request_id: str, stage: str, progress: int, message: str) -> None:
    """Notifica status de uma thread síncrona.
    
    Adiciona a atualização à fila thread-safe para ser processada
    pelo loop assíncrono principal.
    """
    if not request_id:
        return
    
    # Atualiza status em memória
    set_status(request_id, stage, progress, message)
    
    # Adiciona à fila para envio via WebSocket
    try:
        _status_queue.put_nowait((request_id, stage, progress, message))
    except queue.Full:
        logger.warning(f"Fila de status cheia, descartando atualização para {request_id}")


async def update_status_with_websocket(
    request_id: str, stage: str, progress: int, message: str = ""
) -> None:
    """Atualiza status e envia via WebSocket.
    
    Esta função combina set_status() com websocket_manager.notify_status_update()
    para garantir que o frontend receba atualizações em tempo real.
    Trata erros de WebSocket graciosamente para não quebrar o fluxo.
    """
    # Sempre atualiza o status em memória
    set_status(request_id, stage, progress, message)
    
    # Tenta enviar via WebSocket (não bloqueia se falhar)
    try:
        from app.websocket.manager import websocket_manager
        await websocket_manager.notify_status_update(request_id, stage, message, progress)
    except Exception as e:
        # Loga mas não quebra o fluxo se WebSocket falhar
        logger.debug(f"Erro ao enviar status via WebSocket para {request_id}: {e}")

