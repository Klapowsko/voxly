from pathlib import Path

from anyio import to_thread
import torch
import whisper

from app.config import Settings


async def transcribe_file(path: Path, settings: Settings) -> str:
    """Transcreve áudio usando Whisper open source local."""
    
    def _run() -> str:
        # Detecta device (auto, cuda ou cpu)
        if settings.whisper_device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = settings.whisper_device
        
        if device == "cpu":
            print("Aviso: GPU não disponível, usando CPU (será mais lento)")
        
        # Carrega o modelo Whisper
        model = whisper.load_model(settings.whisper_model, device=device)
        
        # Ajustes para acelerar inferência
        options = dict(
            fp16=True if device == "cuda" else False,  # fp16 só funciona em GPU
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.2,
            logprob_threshold=-1.0,
        )
        
        # Transcreve o arquivo
        result = model.transcribe(str(path), **options)
        
        return result.get("text", "").strip()
    
    return await to_thread.run_sync(_run)
