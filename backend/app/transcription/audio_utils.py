"""Utilitários para manipulação de áudio (duração, divisão em chunks)."""
import subprocess
from pathlib import Path


def get_audio_duration(audio_path: Path) -> float:
    """Obtém a duração do áudio em segundos usando ffprobe.
    
    Args:
        audio_path: Caminho do arquivo de áudio
        
    Returns:
        Duração em segundos (float)
        
    Raises:
        RuntimeError: Se não conseguir obter duração
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        duration_str = result.stdout.strip()
        if not duration_str:
            raise RuntimeError(f"Não foi possível obter duração do áudio: {audio_path}")
        duration = float(duration_str)
        return duration
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Erro ao executar ffprobe: {e.stderr}") from e
    except ValueError as e:
        raise RuntimeError(f"Erro ao converter duração para float: {duration_str}") from e


def split_audio_into_chunks(
    audio_path: Path,
    chunk_duration: int,
    output_dir: Path,
    request_id: str,
) -> list[Path]:
    """Divide áudio em chunks de duração especificada usando ffmpeg.
    
    Args:
        audio_path: Caminho do arquivo de áudio original
        chunk_duration: Duração de cada chunk em segundos (ex: 600 para 10 minutos)
        output_dir: Diretório onde salvar os chunks
        request_id: ID da requisição para nomear os arquivos
        
    Returns:
        Lista de caminhos dos chunks na ordem correta
        
    Raises:
        RuntimeError: Se não conseguir dividir o áudio
    """
    # Cria diretório de chunks se não existir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Obtém extensão do arquivo original
    ext = audio_path.suffix.lower()
    if not ext:
        ext = ".mp3"  # Fallback
    
    # Obtém duração total do áudio
    total_duration = get_audio_duration(audio_path)
    
    # Calcula número de chunks
    num_chunks = int(total_duration / chunk_duration) + (1 if total_duration % chunk_duration > 0 else 0)
    
    chunks = []
    
    for i in range(num_chunks):
        start_time = i * chunk_duration
        chunk_path = output_dir / f"{request_id}_chunk_{i:03d}{ext}"
        
        # Comando ffmpeg para extrair chunk
        # Usa -c copy para evitar re-encoding (mais rápido)
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-ss", str(start_time),
            "-t", str(chunk_duration),
            "-c", "copy",  # Copia sem re-encoding
            "-avoid_negative_ts", "make_zero",  # Evita timestamps negativos
            "-y",  # Sobrescreve se existir
            str(chunk_path)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            chunks.append(chunk_path)
        except subprocess.CalledProcessError as e:
            # Se o último chunk falhar (pode ser porque excede a duração), tenta sem -t
            if i == num_chunks - 1:
                # Último chunk: pega o restante sem especificar duração
                cmd_last = [
                    "ffmpeg",
                    "-i", str(audio_path),
                    "-ss", str(start_time),
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    "-y",
                    str(chunk_path)
                ]
                try:
                    subprocess.run(
                        cmd_last,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    chunks.append(chunk_path)
                except subprocess.CalledProcessError as e2:
                    raise RuntimeError(f"Erro ao criar último chunk: {e2.stderr}") from e2
            else:
                raise RuntimeError(f"Erro ao criar chunk {i}: {e.stderr}") from e
    
    return chunks

