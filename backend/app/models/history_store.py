from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Iterable, List, Optional


@dataclass
class TranscriptionRecord:
    id: str
    filename: str
    created_at: str
    audio_path: str
    transcript_path: str
    markdown_path: str
    transcript_preview: str | None = None
    status: str = "done"

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionRecord":
        return cls(**data)


class HistoryStore:
    """Armazena histórico de transcrições em arquivo JSON sob data_dir."""

    def __init__(self, base_dir: Path) -> None:
        self._path = base_dir / "history.json"
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[TranscriptionRecord]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [TranscriptionRecord.from_dict(item) for item in data]
        except Exception:
            # Em caso de arquivo corrompido, retorna lista vazia para não quebrar API
            return []

    def _save(self, records: Iterable[TranscriptionRecord]) -> None:
        serializable = [asdict(record) for record in records]
        self._path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, record: TranscriptionRecord) -> TranscriptionRecord:
        with self._lock:
            records = self._load()
            # substitui se já existir o mesmo id
            records = [r for r in records if r.id != record.id]
            records.append(record)
            # ordena por data desc
            records.sort(key=lambda r: r.created_at, reverse=True)
            self._save(records)
            return record

    def list(self) -> List[TranscriptionRecord]:
        return self._load()

    def get(self, record_id: str) -> Optional[TranscriptionRecord]:
        for record in self._load():
            if record.id == record_id:
                return record
        return None

    def delete(self, record_id: str) -> Optional[TranscriptionRecord]:
        with self._lock:
            records = self._load()
            removed: Optional[TranscriptionRecord] = None
            remaining = []
            for record in records:
                if record.id == record_id:
                    removed = record
                    continue
                remaining.append(record)
            if removed is not None:
                self._save(remaining)
            return removed


def build_preview(text: str, size: int = 240) -> str:
    """Retorna um preview curto do texto."""
    if len(text) <= size:
        return text
    return text[: size - 3].rstrip() + "..."


def now_iso() -> str:
    return datetime.utcnow().isoformat()

