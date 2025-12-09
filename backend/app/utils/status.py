"""Sistema de rastreamento de status para requisições."""
from typing import Dict, Optional
from datetime import datetime

# Armazena status em memória (em produção, usar Redis ou similar)
_status_store: Dict[str, Dict] = {}


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

