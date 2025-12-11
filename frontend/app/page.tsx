"use client";

import { useState, useRef, useEffect, ChangeEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import ScreenShareIcon from "@mui/icons-material/ScreenShare";
import { useWebSocket } from "./hooks/useWebSocket";

type Status = "idle" | "recording" | "capturing_system" | "ready" | "uploading" | "processing" | "transcribing" | "generating" | "done" | "error";

interface Result {
  request_id: string;
  transcript_pt: string;
  transcript_original?: string | null;
  language_detected?: string;
  translated?: boolean;
  markdown: string;
  markdown_file: string;
  download_url: string;
  transcript_file?: string;
  transcript_original_file?: string | null;
}

interface ProgressStatus {
  stage: string;
  progress: number;
  message: string;
  updated_at: string;
}

export default function Home() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("idle");
  const [recordingTime, setRecordingTime] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressStatus | null>(null);
  const [currentRequestId, setCurrentRequestId] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingSource, setPendingSource] = useState<"recording" | "upload" | "system_audio" | null>(null);
  const [systemAudioSupported, setSystemAudioSupported] = useState<boolean>(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldPersistRecordingRef = useRef(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;
  const apiToken = process.env.NEXT_PUBLIC_API_TOKEN as string;
  
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL não está configurada. Configure no arquivo .env");
  }
  
  if (!apiToken) {
    throw new Error("NEXT_PUBLIC_API_TOKEN não está configurada. Configure no arquivo .env");
  }

  // Conecta ao WebSocket quando há um request_id ativo
  const { lastMessage } = useWebSocket({
    requestId: currentRequestId,
    enabled: !!currentRequestId,
    onMessage: (message) => {
      console.log("Mensagem WebSocket recebida:", message);
      if (message.type === "status_update") {
        // Atualiza progresso em tempo real
        const newProgress = {
          stage: message.status,
          progress: message.progress || 0,
          message: message.message || "",
          updated_at: new Date().toISOString(),
        };
        setProgress(newProgress);

        // Se concluído, redireciona para histórico
        if (message.status === "done") {
          console.log("Processamento concluído, redirecionando para histórico...");
          // Limpa o intervalo de verificação de status
          if (statusPollIntervalRef.current) {
            clearInterval(statusPollIntervalRef.current);
            statusPollIntervalRef.current = null;
          }
          setStatus("done");
          setProgress({
            stage: "done",
            progress: 100,
            message: "Processamento concluído! Redirecionando...",
            updated_at: new Date().toISOString(),
          });
          // Redireciona imediatamente
          router.push("/history");
        } else if (message.status === "error") {
          // Limpa o intervalo de verificação de status
          if (statusPollIntervalRef.current) {
            clearInterval(statusPollIntervalRef.current);
            statusPollIntervalRef.current = null;
          }
          setStatus("error");
          setError(message.message || "Erro no processamento");
        } else {
          // Mantém status como "processing" durante o processamento
          if (status !== "processing") {
            setStatus("processing");
          }
        }
      }
    },
  });

  // Verifica suporte para captura de áudio do sistema
  useEffect(() => {
    // Só executa no cliente (navegador do usuário)
    if (typeof window === "undefined") {
      return;
    }

    // Aguarda um pouco para garantir que está no cliente
    const checkSupport = () => {
      try {
        if (typeof navigator === "undefined") {
          console.log("navigator não disponível (SSR?)");
          setSystemAudioSupported(false);
          return;
        }

        if (!navigator.mediaDevices) {
          const isSecure = window.location.protocol === "https:" || window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
          console.log("navigator.mediaDevices não disponível", {
            protocol: window.location.protocol,
            hostname: window.location.hostname,
            isSecure,
            userAgent: navigator.userAgent,
            reason: !isSecure ? "A API requer HTTPS ou localhost" : "Navegador não suporta mediaDevices"
          });
          setSystemAudioSupported(false);
          return;
        }

        const hasGetDisplayMedia = typeof navigator.mediaDevices.getDisplayMedia === "function";
        setSystemAudioSupported(hasGetDisplayMedia);
        
        console.log("Suporte de captura de áudio do sistema:", {
          hasGetDisplayMedia,
          userAgent: navigator.userAgent,
          protocol: window.location.protocol,
          hostname: window.location.hostname,
          supported: hasGetDisplayMedia,
        });
      } catch (error) {
        console.error("Erro ao verificar suporte:", error);
        setSystemAudioSupported(false);
      }
    };

    // Executa imediatamente e também após um pequeno delay para garantir
    checkSupport();
    const timeout = setTimeout(checkSupport, 100);
    
    return () => clearTimeout(timeout);
  }, []);

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
      if (typeof window === "undefined" || !navigator?.mediaDevices) {
        setError("Recursos de gravação não disponíveis neste ambiente.");
        setStatus("error");
        return;
      }
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

  const startSystemAudioCapture = async () => {
    try {
      // Verifica se está no cliente
      if (typeof window === "undefined" || typeof navigator === "undefined") {
        setError("Recursos de captura não disponíveis neste ambiente.");
        setStatus("error");
        return;
      }

      // Verifica se está em contexto seguro (HTTPS ou localhost)
      const isSecure = window.location.protocol === "https:" || 
                       window.location.hostname === "localhost" || 
                       window.location.hostname === "127.0.0.1";
      
      if (!isSecure) {
        setError("A captura de áudio do sistema requer HTTPS. Acesse a página via HTTPS ou use localhost.");
        setStatus("error");
        return;
      }

      // Verifica suporte antes de tentar
      if (!navigator.mediaDevices) {
        setError("Seu navegador não suporta a API de mídia. Use um navegador moderno como Chrome ou Edge.");
        setStatus("error");
        return;
      }

      if (typeof navigator.mediaDevices.getDisplayMedia !== "function") {
        setError("Seu navegador não suporta captura de áudio do sistema. Use Chrome ou Edge.");
        setStatus("error");
        return;
      }

      // Tenta primeiro apenas com áudio (se suportado)
      // Se falhar, tenta com vídeo também (alguns navegadores exigem)
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getDisplayMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            sampleRate: 44100,
          },
          video: false,
        });
      } catch (audioOnlyError) {
        // Se falhar com apenas áudio, tenta com vídeo também
        // (alguns navegadores/plataformas exigem vídeo mesmo que não usemos)
        console.log("Tentativa apenas com áudio falhou, tentando com vídeo também:", audioOnlyError);
        stream = await navigator.mediaDevices.getDisplayMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            sampleRate: 44100,
          },
          video: {
            displaySurface: "browser", // Preferência por abas do navegador
          },
        });
        
        // Para as tracks de vídeo imediatamente (não precisamos delas)
        stream.getVideoTracks().forEach((track) => {
          track.stop();
        });
      }

      // Verifica se há tracks de áudio
      const audioTracks = stream.getAudioTracks();
      if (audioTracks.length === 0) {
        stream.getTracks().forEach((track) => track.stop());
        setError("Nenhuma fonte de áudio foi selecionada. Tente novamente e selecione uma aba ou janela com áudio.");
        setStatus("error");
        return;
      }

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4",
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      shouldPersistRecordingRef.current = false;

      // Para o stream quando o usuário para de compartilhar
      audioTracks.forEach((track) => {
        track.onended = () => {
          if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
            shouldPersistRecordingRef.current = true;
            mediaRecorderRef.current.stop();
          }
        };
      });

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
          setError("Nenhum áudio capturado. Tente novamente.");
          setStatus("error");
          return;
        }

        const mimeType = mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const extension = mimeType.includes("webm") ? "webm" : "mp4";
        const audioFile = new File([audioBlob], `system_audio.${extension}`, { type: mimeType });

        setPendingFile(audioFile);
        setPendingSource("system_audio");
        setStatus("ready");
        setError(null);
      };

      mediaRecorder.onerror = (event) => {
        console.error("Erro no MediaRecorder:", event);
        setError("Erro ao capturar áudio do sistema.");
        setStatus("error");
      };

      mediaRecorder.start(500);
      setStatus("capturing_system");
      setRecordingTime(0);
      setError(null);
      setResult(null);

      timerIntervalRef.current = setInterval(() => {
        setRecordingTime((prev: number) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error("Erro ao capturar áudio do sistema:", err);
      if (err instanceof Error) {
        if (err.name === "NotAllowedError") {
          setError("Permissão negada. Você precisa permitir o compartilhamento de áudio/vídeo.");
        } else if (err.name === "NotFoundError") {
          setError("Nenhuma fonte de áudio encontrada. Certifique-se de que há áudio tocando.");
        } else if (err.name === "NotSupportedError" || err.message?.includes("Not supported")) {
          setError("Captura de áudio do sistema não é suportada nesta plataforma/navegador. Tente usar Windows/Mac ou uma versão mais recente do Chrome.");
        } else if (err.name === "AbortError") {
          // Usuário cancelou - não é um erro
          setStatus("idle");
          setError(null);
          return;
        } else {
          setError(`Erro ao capturar áudio: ${err.message || err.name || "Erro desconhecido"}`);
        }
      } else {
        setError("Erro desconhecido ao capturar áudio do sistema.");
      }
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

      const data = await response.json();
      
      // Nova resposta assíncrona: 202 Accepted com status "processing"
      if (response.status === 202 || data.status === "processing") {
        setCurrentRequestId(data.request_id);
        setStatus("processing");
        setProgress({ 
          stage: "processing", 
          progress: 10, 
          message: data.message || "Processamento iniciado em background...", 
          updated_at: new Date().toISOString() 
        });
        setPendingFile(null);
        setPendingSource(null);
        // WebSocket será conectado automaticamente via hook useWebSocket
        
        // Fallback: verifica periodicamente se o processamento terminou (caso WebSocket falhe)
        // Limpa intervalo anterior se existir
        if (statusPollIntervalRef.current) {
          clearInterval(statusPollIntervalRef.current);
        }
        
        statusPollIntervalRef.current = setInterval(async () => {
          try {
            const statusResp = await fetch(`${apiUrl}/api/status/${data.request_id}`, {
              headers: { "X-API-TOKEN": apiToken },
            });
            if (statusResp.ok) {
              const statusData = await statusResp.json();
              if (statusData.stage === "done") {
                if (statusPollIntervalRef.current) {
                  clearInterval(statusPollIntervalRef.current);
                  statusPollIntervalRef.current = null;
                }
                console.log("Status verificado: done, redirecionando...");
                setStatus("done");
                setProgress({
                  stage: "done",
                  progress: 100,
                  message: "Processamento concluído! Redirecionando...",
                  updated_at: new Date().toISOString(),
                });
                router.push("/history");
              } else if (statusData.stage === "error") {
                if (statusPollIntervalRef.current) {
                  clearInterval(statusPollIntervalRef.current);
                  statusPollIntervalRef.current = null;
                }
                setStatus("error");
                setError(statusData.message || "Erro no processamento");
              }
            }
          } catch (err) {
            // Ignora erros de verificação
          }
        }, 3000); // Verifica a cada 3 segundos
        
        return;
      }

      // Resposta antiga (síncrona) - mantém compatibilidade
      const resultData: Result = data;
      setCurrentRequestId(resultData.request_id);
      setResult(resultData);
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
      if (typeof window === "undefined" || typeof document === "undefined") {
        setError("Download não disponível neste ambiente.");
        return;
      }
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
      case "capturing_system":
        return "Capturando áudio do sistema";
      case "ready":
        return "Pronto para enviar";
      case "uploading":
        return "Enviando";
      case "processing":
        return "Processando";
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
                  <Stack direction="row" spacing={1} flexWrap="wrap">
                    <Button variant="contained" startIcon={<MicIcon />} onClick={startRecording}>
                      Gravar
                    </Button>
                    <Button
                      variant={systemAudioSupported ? "contained" : "outlined"}
                      color="secondary"
                      startIcon={<ScreenShareIcon />}
                      onClick={startSystemAudioCapture}
                      disabled={!systemAudioSupported}
                      title={systemAudioSupported ? "" : "Seu navegador não suporta captura de áudio do sistema. Use Chrome ou Edge."}
                    >
                      Capturar Áudio do Sistema
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<UploadFileIcon />}
                      component="label"
                    >
                      Upload
                      <input type="file" hidden accept="audio/*,video/*" onChange={handleFileSelect} />
                    </Button>
                  </Stack>
                )}

                {(status === "recording" || status === "capturing_system") && (
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

                {(status === "uploading" || status === "processing" || status === "transcribing" || status === "generating") && (
                  <Stack flex={1} spacing={1}>
                    <LinearProgress variant="determinate" value={progress?.progress || 0} />
                    <Typography variant="body2" color="text.secondary">
                      {progress?.message ||
                        (status === "uploading" && "Enviando áudio...") ||
                        (status === "processing" && "Processando em background...") ||
                        (status === "transcribing" && "Transcrevendo com Whisper...") ||
                        (status === "generating" && "Gerando tópicos em Markdown...") ||
                        ""}
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
                <Alert 
                  severity="error" 
                  sx={{ 
                    mt: 2,
                    background: "rgba(244, 67, 54, 0.2)",
                    backdropFilter: "blur(15px) saturate(180%)",
                    WebkitBackdropFilter: "blur(15px) saturate(180%)",
                    border: "1px solid rgba(244, 67, 54, 0.4)",
                  }}
                >
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
                  {pendingFile.name}{" "}
                  {pendingSource === "recording"
                    ? "(gravado agora)"
                    : pendingSource === "system_audio"
                    ? "(áudio do sistema)"
                    : "(upload)"}
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
                      Transcrição {result.language_detected ? `(idioma detectado: ${result.language_detected}${result.translated ? " → traduzido para pt-BR" : ""})` : ""}
                    </Typography>
                    <Paper 
                      variant="outlined" 
                      sx={{ 
                        p: 2, 
                        maxHeight: 240, 
                        overflow: "auto", 
                        background: "rgba(255, 255, 255, 0.08)",
                        backdropFilter: "blur(25px) saturate(200%)",
                        WebkitBackdropFilter: "blur(25px) saturate(200%)",
                      }}
                    >
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                        {result.transcript_pt}
                      </Typography>
                    </Paper>
                  </Box>

                  {result.translated && result.transcript_original && (
                    <Box>
                      <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                        Transcrição original
                      </Typography>
                      <Paper 
                        variant="outlined" 
                        sx={{ 
                          p: 2, 
                          maxHeight: 240, 
                          overflow: "auto", 
                          background: "rgba(255, 255, 255, 0.08)",
                          backdropFilter: "blur(25px) saturate(200%)",
                          WebkitBackdropFilter: "blur(25px) saturate(200%)",
                        }}
                      >
                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                          {result.transcript_original}
                        </Typography>
                      </Paper>
                    </Box>
                  )}

                  <Box>
                    <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                      Tópicos (Markdown)
                    </Typography>
                    <Paper 
                      variant="outlined" 
                      sx={{ 
                        p: 2, 
                        maxHeight: 360, 
                        overflow: "auto", 
                        background: "rgba(255, 255, 255, 0.08)",
                        backdropFilter: "blur(25px) saturate(200%)",
                        WebkitBackdropFilter: "blur(25px) saturate(200%)",
                      }}
                    >
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

