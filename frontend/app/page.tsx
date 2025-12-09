"use client";

import { useState, useRef, useEffect, ChangeEvent } from "react";

type Status = "idle" | "recording" | "uploading" | "transcribing" | "generating" | "done" | "error";

interface Result {
  request_id: string;
  transcript: string;
  markdown: string;
  markdown_file: string;
  download_url: string;
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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const statusPollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Next.js disponibiliza process.env automaticamente no cliente
  const apiUrl = (process.env.NEXT_PUBLIC_API_URL as string) || "http://localhost:8000";
  const apiToken = (process.env.NEXT_PUBLIC_API_TOKEN as string) || "dev-token";
  
  // Debug: verificar se as variáveis estão sendo lidas
  useEffect(() => {
    console.log("API URL:", apiUrl);
    console.log("API Token:", apiToken ? "***" + apiToken.slice(-4) : "não definido");
  }, [apiUrl, apiToken]);

  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
      if (statusPollIntervalRef.current) {
        clearInterval(statusPollIntervalRef.current);
      }
    };
  }, []);

  // Polling de status quando há uma requisição em andamento
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
            
            // Atualiza status baseado no stage
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
              // Atualiza status baseado no stage
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

      // Poll a cada 1 segundo
      statusPollIntervalRef.current = setInterval(pollStatus, 1000);
      pollStatus(); // Primeira chamada imediata

      return () => {
        if (statusPollIntervalRef.current) {
          clearInterval(statusPollIntervalRef.current);
          statusPollIntervalRef.current = null;
        }
      };
    }
  }, [currentRequestId, status, apiUrl, apiToken]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4",
      });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.onerror = (event) => {
        console.error("Erro no MediaRecorder:", event);
        setError("Erro ao gravar áudio.");
        setStatus("error");
      };

      // Inicia com timeslice para garantir que os chunks sejam emitidos
      mediaRecorder.start(1000); // Emite chunks a cada 1 segundo
      setStatus("recording");
      setRecordingTime(0);
      setError(null);

      timerIntervalRef.current = setInterval(() => {
        setRecordingTime((prev: number) => prev + 1);
      }, 1000);
    } catch (err) {
      setError("Erro ao acessar o microfone. Verifique as permissões.");
      setStatus("error");
    }
  };

  const stopRecording = () => {
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    // Não para o MediaRecorder aqui, deixa o handleFinishRecording fazer isso
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
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
      // Headers devem ser enviados mesmo com FormData
      const headers: HeadersInit = {
        "X-API-TOKEN": apiToken,
      };

      console.log("Enviando requisição para:", `${apiUrl}/api/transcribe`);
      console.log("Token sendo enviado:", apiToken ? "***" + apiToken.slice(-4) : "não definido");

      const response = await fetch(`${apiUrl}/api/transcribe`, {
        method: "POST",
        headers: headers,
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
      
      // Limpa polling após conclusão
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

  const handleFinishRecording = async () => {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      setError("Nenhuma gravação em andamento.");
      setStatus("error");
      return;
    }

    // Para o timer primeiro
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }

    // Aguarda o MediaRecorder parar e emitir os chunks finais
    return new Promise<void>((resolve) => {
      const mediaRecorder = mediaRecorderRef.current;
      if (!mediaRecorder) {
        setError("Erro ao finalizar gravação.");
        setStatus("error");
        resolve();
        return;
      }

      // Força a emissão do último chunk
      if (mediaRecorder.state === "recording") {
        mediaRecorder.requestData();
      }

      mediaRecorder.onstop = () => {
        // Para todas as tracks do stream
        if (mediaRecorder.stream) {
          mediaRecorder.stream.getTracks().forEach((track: MediaStreamTrack) => track.stop());
        }

        // Verifica se há chunks coletados
        if (audioChunksRef.current.length === 0) {
          setError("Nenhum áudio gravado. Tente gravar novamente.");
          setStatus("error");
          resolve();
          return;
        }

        // Cria o blob e faz upload
        const mimeType = mediaRecorder.mimeType || "audio/webm";
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        const extension = mimeType.includes("webm") ? "webm" : "mp4";
        const audioFile = new File([audioBlob], `recording.${extension}`, { type: mimeType });
        
        handleFileUpload(audioFile).finally(() => resolve());
      };

      // Para a gravação
      if (mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
      } else {
        // Se já estava parado, processa os chunks existentes
        if (audioChunksRef.current.length > 0) {
          const mimeType = mediaRecorder.mimeType || "audio/webm";
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
          const extension = mimeType.includes("webm") ? "webm" : "mp4";
          const audioFile = new File([audioBlob], `recording.${extension}`, { type: mimeType });
          handleFileUpload(audioFile).finally(() => resolve());
        } else {
          setError("Nenhum áudio gravado.");
          setStatus("error");
          resolve();
        }
      }
    });
  };

  const handleFileSelect = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  const reset = () => {
    setStatus("idle");
    setRecordingTime(0);
    setResult(null);
    setError(null);
    setProgress(null);
    setCurrentRequestId(null);
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-lg shadow-xl p-8">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">
            Gravação e Transcrição de Áudio
          </h1>
          <p className="text-gray-600 mb-8">
            Grave um áudio ou faça upload de um arquivo para transcrever e gerar tópicos em Markdown
          </p>

          {/* Status e controles */}
          <div className="mb-6">
            <div className="flex items-center justify-center gap-4 mb-4">
              {status === "idle" && (
                <button
                  onClick={startRecording}
                  className="px-6 py-3 bg-red-500 hover:bg-red-600 text-white rounded-lg font-semibold transition-colors shadow-md"
                >
                  🎤 Gravar
                </button>
              )}

              {status === "recording" && (
                <>
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 bg-red-500 rounded-full animate-pulse"></div>
                    <span className="text-2xl font-mono font-bold text-red-600">
                      {formatTime(recordingTime)}
                    </span>
                  </div>
                  <button
                    onClick={handleFinishRecording}
                    className="px-6 py-3 bg-green-500 hover:bg-green-600 text-white rounded-lg font-semibold transition-colors shadow-md"
                  >
                    ✓ Concluir
                  </button>
                </>
              )}

              {(status === "uploading" || status === "transcribing" || status === "generating") && (
                <div className="w-full max-w-md mx-auto">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
                    <span className="text-lg text-gray-700 flex-1">
                      {progress?.message || 
                        (status === "uploading" && "Enviando áudio...") ||
                        (status === "transcribing" && "Transcrevendo com Whisper...") ||
                        (status === "generating" && "Gerando tópicos em Markdown...")}
                    </span>
                  </div>
                  
                  {/* Barra de progresso */}
                  <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
                    <div
                      className="bg-indigo-600 h-3 rounded-full transition-all duration-300 ease-out"
                      style={{
                        width: `${progress?.progress || 0}%`,
                      }}
                    ></div>
                  </div>
                  
                  {/* Porcentagem */}
                  <div className="text-center">
                    <span className="text-sm font-semibold text-indigo-600">
                      {progress?.progress || 0}%
                    </span>
                    {progress?.stage && (
                      <span className="text-xs text-gray-500 ml-2">
                        ({progress.stage})
                      </span>
                    )}
                  </div>
                </div>
              )}

              {status === "done" && (
                <button
                  onClick={reset}
                  className="px-6 py-3 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg font-semibold transition-colors shadow-md"
                >
                  🔄 Nova Gravação
                </button>
              )}

              {status === "error" && (
                <button
                  onClick={reset}
                  className="px-6 py-3 bg-gray-500 hover:bg-gray-600 text-white rounded-lg font-semibold transition-colors shadow-md"
                >
                  Tentar Novamente
                </button>
              )}
            </div>

            {/* Upload manual */}
            {status === "idle" && (
              <div className="mt-4">
                <label className="block text-center">
                  <span className="text-gray-700 mr-2">ou</span>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleFileSelect}
                    className="hidden"
                    id="file-upload"
                  />
                  <button
                    onClick={() => document.getElementById("file-upload")?.click()}
                    className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded-lg font-medium transition-colors"
                  >
                    📁 Fazer Upload de Arquivo
                  </button>
                </label>
              </div>
            )}
          </div>

          {/* Mensagem de erro */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-700">{error}</p>
            </div>
          )}

          {/* Resultado */}
          {result && (
            <div className="mt-8 space-y-6">
              <div className="border-t pt-6">
                <h2 className="text-xl font-semibold text-gray-800 mb-4">Resultado</h2>

                <div className="mb-4">
                  <button
                    onClick={() => handleDownload(result.download_url, result.markdown_file)}
                    className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg font-medium transition-colors shadow-md"
                  >
                    📥 Baixar Markdown ({result.markdown_file})
                  </button>
                </div>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">Transcrição:</h3>
                    <div className="bg-gray-50 p-4 rounded-lg border max-h-48 overflow-y-auto">
                      <p className="text-gray-700 whitespace-pre-wrap">{result.transcript}</p>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">Tópicos em Markdown:</h3>
                    <div className="bg-gray-50 p-4 rounded-lg border max-h-96 overflow-y-auto">
                      <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
                        {result.markdown}
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

