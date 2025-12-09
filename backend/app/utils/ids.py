from uuid import uuid4


def new_request_id() -> str:
    """Gera um identificador curto para requisições."""
    return uuid4().hex[:12]

