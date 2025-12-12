"""Utilitários compartilhados para o módulo de transcrição."""


def notify_status_sync(request_id: str | None, stage: str, progress: int, message: str) -> None:
    """Helper para notificar status via WebSocket em contexto síncrono.
    
    Args:
        request_id: ID da requisição
        stage: Estágio do processamento
        progress: Progresso (0-100)
        message: Mensagem de status
    """
    if not request_id:
        return
    from app.utils.status import notify_status_from_thread
    notify_status_from_thread(request_id, stage, progress, message)

