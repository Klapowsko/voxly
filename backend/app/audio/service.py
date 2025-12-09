from pathlib import Path

from fastapi import UploadFile

from app.config import Settings

CHUNK_SIZE = 1024 * 1024  # 1MB


async def save_upload(upload: UploadFile, settings: Settings, request_id: str) -> Path:
    """Salva o arquivo de upload no diretório de uploads."""
    filename = upload.filename or "audio"
    sanitized_name = filename.replace("/", "_").replace("\\", "_")
    dest_path = settings.uploads_dir / f"{request_id}_{sanitized_name}"

    with dest_path.open("wb") as dest_file:
        while True:
            chunk = await upload.read(CHUNK_SIZE)
            if not chunk:
                break
            dest_file.write(chunk)

    await upload.close()
    return dest_path


