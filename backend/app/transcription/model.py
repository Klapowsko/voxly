"""Gerenciamento de cache e carregamento de modelos Whisper."""
from typing import Dict

import whisper

# Cache global de modelos Whisper (evita recarregar a cada transcrição)
_model_cache: Dict[str, whisper.Whisper] = {}


def get_cached_model(model_name: str, device: str) -> whisper.Whisper:
    """Retorna modelo Whisper do cache ou carrega se não existir.
    
    Args:
        model_name: Nome do modelo Whisper
        device: Device a ser usado ('cuda' ou 'cpu')
        
    Returns:
        Modelo Whisper carregado
    """
    cache_key = f"{model_name}_{device}"
    if cache_key not in _model_cache:
        print(f"Carregando modelo Whisper {model_name} em {device} (primeira vez)...")
        _model_cache[cache_key] = whisper.load_model(model_name, device=device)
        print(f"Modelo {model_name} carregado e cacheado.")
    return _model_cache[cache_key]

