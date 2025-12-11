"use client";

import { useEffect, useRef, useState } from "react";

interface WebSocketMessage {
  type: "status_update" | "history_update";
  request_id: string;
  status: string;
  message?: string;
  progress?: number;
}

interface UseWebSocketOptions {
  requestId?: string | null;
  onMessage?: (message: WebSocketMessage) => void;
  enabled?: boolean;
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { requestId, onMessage, enabled = true } = options;
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isConnectingRef = useRef(false);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL as string;

  useEffect(() => {
    isMountedRef.current = true;
    
    if (!enabled || !apiUrl) {
      return;
    }

    // Constrói URL do WebSocket
    let wsUrl: string;
    try {
      const url = new URL(apiUrl);
      const wsProtocol = url.protocol === "https:" ? "wss:" : "ws:";
      wsUrl = requestId
        ? `${wsProtocol}//${url.host}/api/ws/${requestId}`
        : `${wsProtocol}//${url.host}/api/ws`;
    } catch (error) {
      console.error("Erro ao construir URL do WebSocket:", error);
      return;
    }

    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    const connect = () => {
      // Evita múltiplas conexões simultâneas
      if (isConnectingRef.current || (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING)) {
        console.log("Já está conectando, ignorando nova tentativa");
        return;
      }

      // Fecha conexão anterior se existir
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (e) {
          // Ignora erros ao fechar
        }
      }

      try {
        isConnectingRef.current = true;
        console.log(`Conectando WebSocket: ${wsUrl}`);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log("WebSocket conectado");
          isConnectingRef.current = false;
          setIsConnected(true);
          reconnectAttempts = 0;
          // Envia ping para manter conexão viva
          if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
          }
          pingIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send("ping");
            } else {
              if (pingIntervalRef.current) {
                clearInterval(pingIntervalRef.current);
                pingIntervalRef.current = null;
              }
            }
          }, 30000); // Ping a cada 30 segundos
        };

        ws.onmessage = (event) => {
          try {
            if (event.data === "pong") {
              return; // Ignora pong
            }
            const message: WebSocketMessage = JSON.parse(event.data);
            setLastMessage(message);
            if (onMessage) {
              onMessage(message);
            }
          } catch (error) {
            console.error("Erro ao processar mensagem WebSocket:", error);
          }
        };

        ws.onerror = (error) => {
          console.error("Erro no WebSocket:", error);
          isConnectingRef.current = false;
          // Não tenta reconectar imediatamente em caso de erro
          // O onclose vai lidar com a reconexão
        };

        ws.onclose = (event) => {
          console.log("WebSocket desconectado", { code: event.code, reason: event.reason, wasClean: event.wasClean });
          isConnectingRef.current = false;
          
          // Só atualiza estado se o componente ainda estiver montado
          if (isMountedRef.current) {
            setIsConnected(false);
          }

          // Limpa ping interval
          if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
          }

          // Não reconecta se:
          // 1. Componente foi desmontado
          // 2. Foi fechado intencionalmente (código 1000)
          // 3. Já excedeu tentativas
          if (!isMountedRef.current || event.code === 1000 || reconnectAttempts >= maxReconnectAttempts) {
            console.log("Não tentando reconectar WebSocket", { 
              isMounted: isMountedRef.current, 
              code: event.code, 
              attempts: reconnectAttempts 
            });
            return;
          }

          // Tenta reconectar com backoff exponencial
          reconnectAttempts++;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
          console.log(`Tentando reconectar WebSocket em ${delay}ms (tentativa ${reconnectAttempts}/${maxReconnectAttempts})`);
          reconnectTimeoutRef.current = setTimeout(() => {
            // Verifica novamente se ainda está montado antes de reconectar
            if (isMountedRef.current) {
              connect();
            }
          }, delay);
        };
      } catch (error) {
        console.error("Erro ao conectar WebSocket:", error);
        isConnectingRef.current = false;
      }
    };

    connect();

    return () => {
      isMountedRef.current = false;
      console.log("Limpando WebSocket connection");
      isConnectingRef.current = false;
      
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      
      if (wsRef.current) {
        // Fecha com código 1000 (normal closure) para evitar reconexão
        try {
          // Remove handlers para evitar que onclose tente reconectar
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.onopen = null;
          wsRef.current.onmessage = null;
          
          if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
            wsRef.current.close(1000, "Component unmounted");
          }
        } catch (e) {
          // Ignora erros ao fechar
        }
        wsRef.current = null;
      }
    };
  }, [requestId, enabled, apiUrl, onMessage]);

  return { isConnected, lastMessage };
}

