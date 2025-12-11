"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Stack,
  Card,
  CardContent,
  Button,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Grid,
  Paper,
  Alert,
  Box,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import VisibilityIcon from "@mui/icons-material/Visibility";
import RefreshIcon from "@mui/icons-material/Refresh";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CheckIcon from "@mui/icons-material/Check";

interface HistoryItem {
  id: string;
  filename: string;
  title?: string | null;
  created_at: string;
  status: string; // "processing", "done", "error"
  transcript_preview?: string | null;
  markdown_file: string;
  transcript_file: string;
  markdown_url: string;
  transcript_url: string;
  language_detected?: string | null;
  translated?: boolean;
  transcript_original_file?: string | null;
  transcript_original_url?: string | null;
  error_message?: string | null;
}

interface HistoryDetail {
  id: string;
  filename: string;
  title?: string | null;
  created_at: string;
  status: string;
  transcript: string;
  markdown: string;
  markdown_file: string;
  transcript_file: string;
  markdown_url: string;
  transcript_url: string;
  language_detected?: string | null;
  translated?: boolean;
  transcript_original?: string | null;
  transcript_original_file?: string | null;
  transcript_original_url?: string | null;
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const itemsRef = useRef<HistoryItem[]>([]);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;
  const apiToken = process.env.NEXT_PUBLIC_API_TOKEN as string;
  
  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL não está configurada. Configure no arquivo .env");
  }
  
  if (!apiToken) {
    throw new Error("NEXT_PUBLIC_API_TOKEN não está configurada. Configure no arquivo .env");
  }

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiUrl}/api/history`, {
        headers: { "X-API-TOKEN": apiToken },
      });
      if (!resp.ok) {
        throw new Error(`Erro ${resp.status}`);
      }
      const data: HistoryItem[] = await resp.json();
      setItems(data);
      itemsRef.current = data; // Atualiza a ref também
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar histórico");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
    // Polling para atualizar histórico apenas se houver itens em processamento
    const interval = setInterval(() => {
      // Verifica se há itens em processamento usando a ref (sem causar re-render)
      const hasProcessingItems = itemsRef.current.some(item => item.status === "processing");
      if (hasProcessingItems) {
        // Atualiza o histórico se houver itens processando
        fetchHistory();
      }
    }, 10000); // Verifica a cada 10 segundos (menos frequente)
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetail = async (id: string) => {
    setDetailLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${apiUrl}/api/history/${id}`, {
        headers: { "X-API-TOKEN": apiToken },
      });
      if (!resp.ok) {
        throw new Error(`Erro ${resp.status}`);
      }
      const data: HistoryDetail = await resp.json();
      setSelected(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar transcrição");
    } finally {
      setDetailLoading(false);
    }
  };

  const deleteItem = async (id: string) => {
    setDeleting(id);
    setError(null);
    try {
      const resp = await fetch(`${apiUrl}/api/history/${id}`, {
        method: "DELETE",
        headers: { "X-API-TOKEN": apiToken },
      });
      if (!resp.ok) {
        throw new Error(`Erro ${resp.status}`);
      }
      setItems((prev) => {
        const newItems = prev.filter((item) => item.id !== id);
        itemsRef.current = newItems; // Atualiza a ref também
        return newItems;
      });
      if (selected?.id === id) {
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao excluir");
    } finally {
      setDeleting(null);
    }
  };

  const handleDownload = async (url: string, filename: string) => {
    try {
      const resp = await fetch(`${apiUrl}${url}`, {
        headers: { "X-API-TOKEN": apiToken },
      });
      if (!resp.ok) throw new Error(`Erro ${resp.status}`);
      const blob = await resp.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(objUrl);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao baixar arquivo");
    }
  };

  const handleCopy = async (text: string, type: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000); // Remove o feedback após 2 segundos
    } catch (err) {
      setError("Erro ao copiar para clipboard");
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
            <Button component={Link} href="/" color="primary" variant="outlined" size="small">
              Transcrever
            </Button>
            <Button component={Link} href="/history" color="primary" variant="contained" size="small">
              Histórico
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
          <div>
            <Typography variant="h5" fontWeight={700}>
              Histórico de transcrições
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Revise, baixe ou remova transcrições passadas.
            </Typography>
          </div>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={fetchHistory} disabled={loading}>
            Atualizar
          </Button>
        </Stack>

          {error && (
            <Alert 
              severity="error" 
              sx={{ 
                mb: 2,
                background: "rgba(244, 67, 54, 0.2)",
                backdropFilter: "blur(15px) saturate(180%)",
                WebkitBackdropFilter: "blur(15px) saturate(180%)",
                border: "1px solid rgba(244, 67, 54, 0.4)",
              }}
            >
              {error}
            </Alert>
          )}

        {loading ? (
          <Stack alignItems="center" py={6}>
            <CircularProgress />
          </Stack>
        ) : items.length === 0 ? (
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 4, 
              textAlign: "center", 
              background: "rgba(255, 255, 255, 0.08)",
              backdropFilter: "blur(30px) saturate(200%)",
              WebkitBackdropFilter: "blur(30px) saturate(200%)",
            }}
          >
            <Typography>Nenhuma transcrição ainda.</Typography>
          </Paper>
        ) : (
          <Grid container spacing={2}>
            {items.map((item) => (
              <Grid item xs={12} md={6} key={item.id}>
                <Card variant="outlined">
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                      <div>
                        <Typography variant="subtitle1" fontWeight={700}>
                          {item.title || item.filename}
                        </Typography>
                        {item.title && item.title !== item.filename && (
                          <Typography variant="caption" color="text.secondary" display="block">
                            {item.filename}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary">
                          {new Date(item.created_at).toLocaleString()}
                        </Typography>
                        {item.status === "error" && item.error_message && (
                          <Alert severity="error" sx={{ mt: 1, py: 0.5 }}>
                            {item.error_message}
                          </Alert>
                        )}
                        {item.transcript_preview && item.status === "done" && (
                          <Typography variant="body2" color="text.secondary" mt={1}>
                            {item.transcript_preview}
                          </Typography>
                        )}
                        {item.status === "processing" && (
                          <Typography variant="body2" color="text.secondary" mt={1}>
                            Processando transcrição...
                          </Typography>
                        )}
                      </div>
                      <Stack direction="row" spacing={1} alignItems="center">
                        {item.status === "processing" && (
                          <Chip
                            size="small"
                            label="Processando"
                            color="warning"
                            icon={<CircularProgress size={16} />}
                          />
                        )}
                        {item.status === "done" && (
                          <Chip size="small" label="Concluído" color="success" />
                        )}
                        {item.status === "error" && (
                          <Chip size="small" label="Erro" color="error" />
                        )}
                        {item.language_detected && item.status === "done" && (
                          <Chip
                            size="small"
                            label={`${item.language_detected}${item.translated ? " → pt" : ""}`}
                            color="primary"
                            variant="outlined"
                          />
                        )}
                      </Stack>
                    </Stack>

                    <Stack direction="row" spacing={1} mt={2}>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<VisibilityIcon />}
                        onClick={() => openDetail(item.id)}
                        disabled={(item.status === "processing" || item.status === "error") || (detailLoading && selected?.id === item.id)}
                      >
                        Ver
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => handleDownload(item.markdown_url, item.markdown_file)}
                      >
                        Baixar MD
                      </Button>
                      <IconButton
                        color="error"
                        onClick={() => deleteItem(item.id)}
                        disabled={deleting === item.id}
                        aria-label="Excluir"
                      >
                        {deleting === item.id ? <CircularProgress size={18} /> : <DeleteIcon />}
                      </IconButton>
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Container>

      <Dialog open={!!selected} onClose={() => setSelected(null)} fullWidth maxWidth="md">
        <DialogTitle>Transcrição</DialogTitle>
        <DialogContent dividers>
          {detailLoading ? (
            <Stack alignItems="center" py={3}>
              <CircularProgress />
            </Stack>
          ) : selected ? (
            <Stack spacing={2}>
              <Typography variant="subtitle1" fontWeight={700}>
                {selected.title || selected.filename}
              </Typography>
              {selected.title && selected.title !== selected.filename && (
                <Typography variant="caption" color="text.secondary">
                  {selected.filename}
                </Typography>
              )}
              <Typography variant="caption" color="text.secondary">
                {new Date(selected.created_at).toLocaleString()}
              </Typography>
              {selected.language_detected && (
                <Typography variant="body2" color="text.secondary">
                  Idioma: {selected.language_detected} {selected.translated ? "→ traduzido para pt-BR" : ""}
                </Typography>
              )}

              <Box>
                <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="subtitle2" fontWeight={700}>
                    Transcrição
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => handleCopy(selected.transcript, "transcript")}
                    title="Copiar transcrição"
                    sx={{
                      color: copied === "transcript" ? "success.main" : "inherit",
                    }}
                  >
                    {copied === "transcript" ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
                  </IconButton>
                </Stack>
                <Paper 
                  variant="outlined" 
                  sx={{ 
                    p: 2, 
                    maxHeight: 260, 
                    overflow: "auto", 
                    background: "rgba(255, 255, 255, 0.08)",
                    backdropFilter: "blur(25px) saturate(200%)",
                    WebkitBackdropFilter: "blur(25px) saturate(200%)",
                  }}
                >
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {selected.transcript}
                  </Typography>
                </Paper>
              </Box>

              <Box>
                <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="subtitle2" fontWeight={700}>
                    Tópicos (Markdown)
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => handleCopy(selected.markdown, "markdown")}
                    title="Copiar markdown"
                    sx={{
                      color: copied === "markdown" ? "success.main" : "inherit",
                    }}
                  >
                    {copied === "markdown" ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
                  </IconButton>
                </Stack>
                <Paper 
                  variant="outlined" 
                  sx={{ 
                    p: 2, 
                    maxHeight: 260, 
                    overflow: "auto", 
                    background: "rgba(255, 255, 255, 0.08)",
                    backdropFilter: "blur(25px) saturate(200%)",
                    WebkitBackdropFilter: "blur(25px) saturate(200%)",
                  }}
                >
                  <Typography component="pre" variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                    {selected.markdown}
                  </Typography>
                </Paper>
              </Box>

              {selected.translated && selected.transcript_original && (
                <Box>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="subtitle2" fontWeight={700}>
                      Transcrição original
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={() => handleCopy(selected.transcript_original!, "transcript_original")}
                      title="Copiar transcrição original"
                      sx={{
                        color: copied === "transcript_original" ? "success.main" : "inherit",
                      }}
                    >
                      {copied === "transcript_original" ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
                    </IconButton>
                  </Stack>
                  <Paper 
                    variant="outlined" 
                    sx={{ 
                      p: 2, 
                      maxHeight: 260, 
                      overflow: "auto", 
                      background: "rgba(255, 255, 255, 0.08)",
                      backdropFilter: "blur(25px) saturate(200%)",
                      WebkitBackdropFilter: "blur(25px) saturate(200%)",
                    }}
                  >
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                      {selected.transcript_original}
                    </Typography>
                  </Paper>
                </Box>
              )}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          {selected && (
            <>
              <Button onClick={() => handleDownload(selected.markdown_url, selected.markdown_file)}>Baixar MD</Button>
              <Button onClick={() => handleDownload(selected.transcript_url, selected.transcript_file)}>Baixar TXT</Button>
              {selected.translated && selected.transcript_original_url && selected.transcript_original_file && (
                <Button onClick={() => handleDownload(selected.transcript_original_url!, selected.transcript_original_file!)}>
                  Baixar TXT original
                </Button>
              )}
            </>
          )}
          <Button onClick={() => setSelected(null)}>Fechar</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

