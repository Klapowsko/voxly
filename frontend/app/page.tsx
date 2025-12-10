"use client";

import { useState, useRef, useEffect, ChangeEvent } from "react";
import Link from "next/link";
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Card,
  CardContent,
  Stack,
  Button,
  IconButton,
  LinearProgress,
  Alert,
  Chip,
  Divider,
  Box,
  Paper,
} from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import SendIcon from "@mui/icons-material/Send";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import RefreshIcon from "@mui/icons-material/Refresh";

type Status = "idle" | "recording" | "ready" | "uploading" | "transcribing" | "generating" | "done" | "error";

interface Result {
  request_id: string;
  transcript: string;
  markdown: string;
  markdown_file: string;
  download_url: string;
  transcript_file?: string;
}

interface ProgressStatus {
  stage: string;
  progress: number;
  message: string;
  updated_at: string;
}

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [recordingTime, setRecordingTime] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressStatus | null>(null);
  const [currentRequestId, setCurrentRequestId] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingSource, setPendingSource] = useState<"recording" | "upload" | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldPersistRecordingRef = useRef(false);

  const apiUrl = (process.env.NEXT_PUBLIC_API_URL as string) || "http://localhost:8000";
  const apiToken = (process.env.NEXT_PUBLIC_API_TOKEN as string) || "dev-token";

  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
      if (statusPollIntervalRef.current) {
        clearInterval(statusPollIntervalRef.current);
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  useEffect(() => {
    if (currentRequestId && (status === "uploading" || status === "transcribing" || status === "generating")) {
      const pollStatus = async () => {
        try {
          const response = await fetch(`${apiUrl}/api/status/${currentRequestId}`, {
            headers: {
              "X-API-TOKEN": apiToken,
            },
          });
          if (response.ok) {
            const statusData: ProgressStatus = await response.json();
            setProgress(statusData);

            if (statusData.stage === "done") {
              setStatus("done");
              if (statusPollIntervalRef.current) {
                clearInterval(statusPollIntervalRef.current);
                statusPollIntervalRef.current = null;
              }
            } else if (statusData.stage === "error") {
              setStatus("error");
              setError(statusData.message);
              if (statusPollIntervalRef.current) {
                clearInterval(statusPollIntervalRef.current);
                statusPollIntervalRef.current = null;
              }
            } else {
              if (statusData.stage === "uploading") {
                setStatus("uploading");
              } else if (statusData.stage === "transcribing") {
                setStatus("transcribing");
              } else if (statusData.stage === "generating") {
                setStatus("generating");
              }
            }
          }
        } catch (err) {
          console.error("Erro ao buscar status:", err);
        }
      };

      statusPollIntervalRef.current = setInterval(pollStatus, 1000);
      pollStatus();

      return () => {
        if (statusPollIntervalRef.current) {
          clearInterval(statusPollIntervalRef.current);
          statusPollIntervalRef.current = null;
        }
      };
    }
  }, [currentRequestId, status, apiUrl, apiToken]);

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4",
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      shouldPersistRecordingRef.current = false;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        if (!shouldPersistRecordingRef.current) {
          // cancelamento: apenas limpa
          audioChunksRef.current = [];
          return;
        }

        if (audioChunksRef.current.length === 0) {
          setError("Nenhum áudio gravado. Tente novamente.");
          setStatus("error");
          return;
        }

        const mimeType = mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const extension = mimeType.includes("webm") ? "webm" : "mp4";
        const audioFile = new File([audioBlob], `recording.${extension}`, { type: mimeType });

        setPendingFile(audioFile);
        setPendingSource("recording");
        setStatus("ready");
        setError(null);
      };

      mediaRecorder.onerror = (event) => {
        console.error("Erro no MediaRecorder:", event);
        setError("Erro ao gravar áudio.");
        setStatus("error");
      };

      mediaRecorder.start(500);
      setStatus("recording");
      setRecordingTime(0);
      setError(null);
      setResult(null);

      timerIntervalRef.current = setInterval(() => {
        setRecordingTime((prev: number) => prev + 1);
      }, 1000);
    } catch (err) {
      setError("Erro ao acessar o microfone. Verifique as permissões.");
      setStatus("error");
    }
  };

  const stopRecordingAndKeep = () => {
    shouldPersistRecordingRef.current = true;
    stopRecordingInternal();
  };

  const cancelRecording = () => {
    shouldPersistRecordingRef.current = false;
    stopRecordingInternal();
    setStatus("idle");
    setRecordingTime(0);
  };

  const stopRecordingInternal = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  };

  const prepareFileForUpload = (file: File) => {
    setPendingFile(file);
    setPendingSource("upload");
    setStatus("ready");
    setResult(null);
    setError(null);
    setProgress(null);
  };

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      prepareFileForUpload(file);
    }
  };

  const handleSendPending = async () => {
    if (!pendingFile) {
      setError("Nenhum arquivo para enviar.");
      return;
    }
    await handleFileUpload(pendingFile);
  };

  const handleCancelPending = () => {
    setPendingFile(null);
    setPendingSource(null);
    setStatus("idle");
    setResult(null);
    setError(null);
    setProgress(null);
    audioChunksRef.current = [];
  };

  const handleFileUpload = async (file: File) => {
    setStatus("uploading");
    setError(null);
    setResult(null);
    setProgress({ stage: "uploading", progress: 0, message: "Iniciando upload...", updated_at: new Date().toISOString() });
    setCurrentRequestId(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const headers: HeadersInit = {
        "X-API-TOKEN": apiToken,
      };

      const response = await fetch(`${apiUrl}/api/transcribe`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Erro desconhecido" }));
        throw new Error(errorData.detail || `Erro ${response.status}`);
      }

      const data: Result = await response.json();
      setCurrentRequestId(data.request_id);
      setResult(data);
      setStatus("done");
      setProgress({ stage: "done", progress: 100, message: "Processamento concluído!", updated_at: new Date().toISOString() });
      setPendingFile(null);
      setPendingSource(null);

      if (statusPollIntervalRef.current) {
        clearInterval(statusPollIntervalRef.current);
        statusPollIntervalRef.current = null;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao processar áudio");
      setStatus("error");
      setProgress(null);
      setCurrentRequestId(null);
      if (statusPollIntervalRef.current) {
        clearInterval(statusPollIntervalRef.current);
        statusPollIntervalRef.current = null;
      }
    }
  };

  const reset = () => {
    setStatus("idle");
    setRecordingTime(0);
    setResult(null);
    setError(null);
    setProgress(null);
    setCurrentRequestId(null);
    setPendingFile(null);
    setPendingSource(null);
    audioChunksRef.current = [];
    if (statusPollIntervalRef.current) {
      clearInterval(statusPollIntervalRef.current);
      statusPollIntervalRef.current = null;
    }
  };

  const handleDownload = async (downloadUrl: string, filename: string) => {
    try {
      const response = await fetch(`${apiUrl}${downloadUrl}`, {
        method: "GET",
        headers: {
          "X-API-TOKEN": apiToken,
        },
      });

      if (!response.ok) {
        throw new Error(`Erro ao baixar arquivo: ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao baixar arquivo");
      setStatus("error");
    }
  };

  const statusLabel = () => {
    switch (status) {
      case "recording":
        return "Gravando";
      case "ready":
        return "Pronto para enviar";
      case "uploading":
        return "Enviando";
      case "transcribing":
        return "Transcrevendo";
      case "generating":
        return "Gerando tópicos";
      case "done":
        return "Concluído";
      case "error":
        return "Erro";
      default:
        return "Parado";
    }
  };

  return (
    <>
      <AppBar position="static" color="transparent" elevation={0}>
        <Toolbar sx={{ display: "flex", justifyContent: "space-between" }}>
          <Typography variant="h6" fontWeight={700}>
            Voxly
          </Typography>
          <Stack direction="row" spacing={1}>
            <Button component={Link} href="/" color="primary" variant="contained" size="small">
              Transcrever
            </Button>
            <Button component={Link} href="/history" color="primary" variant="outlined" size="small">
              Histórico
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>

      <Container maxWidth="md" sx={{ py: 4 }}>
        <Stack spacing={3}>
          <Card elevation={3}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                <div>
                  <Typography variant="h5" fontWeight={700}>
                    Gravação e Transcrição
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Grave ou selecione um arquivo, revise e envie quando quiser.
                  </Typography>
                </div>
                <Chip label={statusLabel()} color={status === "error" ? "error" : status === "done" ? "success" : "primary"} />
              </Stack>

              <Divider sx={{ my: 2 }} />

              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ xs: "stretch", sm: "center" }}>
                {status === "idle" && (
                  <Stack direction="row" spacing={1}>
                    <Button variant="contained" startIcon={<MicIcon />} onClick={startRecording}>
                      Gravar
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<UploadFileIcon />}
                      component="label"
                    >
                      Upload
                      <input type="file" hidden accept="audio/*" onChange={handleFileSelect} />
                    </Button>
                  </Stack>
                )}

                {status === "recording" && (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip color="error" label={formatTime(recordingTime)} />
                    <Button color="success" variant="contained" startIcon={<StopIcon />} onClick={stopRecordingAndKeep}>
                      Parar e revisar
                    </Button>
                    <Button color="inherit" variant="outlined" startIcon={<DeleteIcon />} onClick={cancelRecording}>
                      Cancelar
                    </Button>
                  </Stack>
                )}

                {status === "ready" && pendingFile && (
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ xs: "stretch", sm: "center" }}>
                    <Chip label={`Pronto: ${pendingFile.name}`} color="primary" />
                    <Button variant="contained" startIcon={<SendIcon />} onClick={handleSendPending}>
                      Enviar
                    </Button>
                    <Button variant="outlined" color="inherit" startIcon={<DeleteIcon />} onClick={handleCancelPending}>
                      Cancelar
                    </Button>
                  </Stack>
                )}

                {(status === "uploading" || status === "transcribing" || status === "generating") && (
                  <Stack flex={1} spacing={1}>
                    <LinearProgress variant="determinate" value={progress?.progress || 0} />
                    <Typography variant="body2" color="text.secondary">
                      {progress?.message ||
                        (status === "uploading" && "Enviando áudio...") ||
                        (status === "transcribing" && "Transcrevendo com Whisper...") ||
                        (status === "generating" && "Gerando tópicos em Markdown...")}
                    </Typography>
                  </Stack>
                )}

                {status === "done" && (
                  <Button variant="outlined" startIcon={<RefreshIcon />} onClick={reset}>
                    Nova transcrição
                  </Button>
                )}

                {status === "error" && (
                  <Button variant="outlined" startIcon={<RefreshIcon />} onClick={reset}>
                    Tentar novamente
                  </Button>
                )}
              </Stack>

              {error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {error}
                </Alert>
              )}
            </CardContent>
          </Card>

          {pendingFile && status === "ready" && (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700}>
                  Arquivo aguardando envio
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {pendingFile.name} {pendingSource === "recording" ? "(gravado agora)" : "(upload)"}
                </Typography>
              </CardContent>
            </Card>
          )}

          {result && (
            <Card elevation={2}>
              <CardContent>
                <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6" fontWeight={700}>
                    Resultado
                  </Typography>
                  <Button variant="contained" onClick={() => handleDownload(result.download_url, result.markdown_file)}>
                    Baixar Markdown
                  </Button>
                </Stack>

                <Stack spacing={2}>
                  <Box>
                    <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                      Transcrição
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, maxHeight: 240, overflow: "auto" }}>
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                        {result.transcript}
                      </Typography>
                    </Paper>
                  </Box>

                  <Box>
                    <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                      Tópicos (Markdown)
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 2, maxHeight: 360, overflow: "auto" }}>
                      <Typography component="pre" variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                        {result.markdown}
                      </Typography>
                    </Paper>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          )}
        </Stack>
      </Container>
    </>
  );
}

