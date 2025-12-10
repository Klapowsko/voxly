"use client";

import { useEffect, useState } from "react";
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

interface HistoryItem {
  id: string;
  filename: string;
  created_at: string;
  status: string;
  transcript_preview?: string | null;
  markdown_file: string;
  transcript_file: string;
  markdown_url: string;
  transcript_url: string;
}

interface HistoryDetail {
  id: string;
  filename: string;
  created_at: string;
  status: string;
  transcript: string;
  markdown: string;
  markdown_file: string;
  transcript_file: string;
  markdown_url: string;
  transcript_url: string;
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const apiUrl = (process.env.NEXT_PUBLIC_API_URL as string) || "http://localhost:8000";
  const apiToken = (process.env.NEXT_PUBLIC_API_TOKEN as string) || "dev-token";

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar histórico");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
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
      setItems((prev) => prev.filter((item) => item.id !== id));
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
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Stack alignItems="center" py={6}>
            <CircularProgress />
          </Stack>
        ) : items.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
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
                          {item.filename}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {new Date(item.created_at).toLocaleString()}
                        </Typography>
                        {item.transcript_preview && (
                          <Typography variant="body2" color="text.secondary" mt={1}>
                            {item.transcript_preview}
                          </Typography>
                        )}
                      </div>
                      <Chip size="small" label={item.status} color={item.status === "done" ? "success" : "default"} />
                    </Stack>

                    <Stack direction="row" spacing={1} mt={2}>
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<VisibilityIcon />}
                        onClick={() => openDetail(item.id)}
                        disabled={detailLoading && selected?.id === item.id}
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
                {selected.filename}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {new Date(selected.created_at).toLocaleString()}
              </Typography>

              <Box>
                <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                  Transcrição
                </Typography>
                <Paper variant="outlined" sx={{ p: 2, maxHeight: 260, overflow: "auto" }}>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {selected.transcript}
                  </Typography>
                </Paper>
              </Box>

              <Box>
                <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                  Tópicos (Markdown)
                </Typography>
                <Paper variant="outlined" sx={{ p: 2, maxHeight: 260, overflow: "auto" }}>
                  <Typography component="pre" variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                    {selected.markdown}
                  </Typography>
                </Paper>
              </Box>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          {selected && (
            <>
              <Button onClick={() => handleDownload(selected.markdown_url, selected.markdown_file)}>Baixar MD</Button>
              <Button onClick={() => handleDownload(selected.transcript_url, selected.transcript_file)}>Baixar TXT</Button>
            </>
          )}
          <Button onClick={() => setSelected(null)}>Fechar</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

