"""Módulo de transcrição de áudio usando Whisper."""

# Exports públicos principais
from app.transcription.background import process_transcription_async
from app.transcription.cleaning import limpar_repeticoes
from app.transcription.service import transcribe_file
from app.transcription.translate import translate_en_to_pt

__all__ = [
    "process_transcription_async",
    "transcribe_file",
    "limpar_repeticoes",
    "translate_en_to_pt",
]
