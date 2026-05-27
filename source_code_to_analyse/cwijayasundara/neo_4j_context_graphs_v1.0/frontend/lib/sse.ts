/**
 * useChat — React hook that streams SSE from `POST /api/chat/stream`.
 * Returns { messages, isStreaming, sendMessage, clearMessages }.
 */

"use client";

import { useState, useCallback, useRef } from "react";
import type { ChatMessage, ChartSpec } from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    sessionIdRef.current = null;
    setIsStreaming(false);
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    let fullText = "";
    let chartSpec: ChartSpec | undefined;

    try {
      const res = await fetch(`${BASE_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionIdRef.current,
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error(errBody?.detail || `Backend error (${res.status})`);
      }

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ") && eventType) {
            try {
              const data = JSON.parse(line.slice(6));
              switch (eventType) {
                case "session_id":
                  sessionIdRef.current = data.session_id;
                  break;

                case "text_delta":
                  fullText += data.text;
                  // Update the streaming assistant message in-place
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last?.role === "assistant") {
                      return [
                        ...prev.slice(0, -1),
                        { ...last, content: fullText },
                      ];
                    }
                    return [
                      ...prev,
                      { role: "assistant", content: fullText },
                    ];
                  });
                  break;

                case "chart":
                  chartSpec = data as ChartSpec;
                  break;

                case "done": {
                  const finalContent = data.response || fullText;
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last?.role === "assistant") {
                      return [
                        ...prev.slice(0, -1),
                        {
                          role: "assistant" as const,
                          content: finalContent,
                          chart_spec: chartSpec,
                        },
                      ];
                    }
                    return [
                      ...prev,
                      {
                        role: "assistant" as const,
                        content: finalContent,
                        chart_spec: chartSpec,
                      },
                    ];
                  });
                  break;
                }

                case "error":
                  throw new Error(data.detail || "Streaming error");
              }
            } catch (parseErr) {
              if (!(parseErr instanceof SyntaxError)) throw parseErr;
            }
            eventType = "";
          }
        }
      }
    } catch (err: unknown) {
      let errorMsg: string;
      if (err instanceof DOMException && err.name === "AbortError") {
        errorMsg = "Request cancelled.";
      } else if (err instanceof Error) {
        errorMsg = err.message;
      } else {
        errorMsg = "Cannot reach the backend.";
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `**Error:** ${errorMsg}` },
      ]);
    } finally {
      abortRef.current = null;
      setIsStreaming(false);
    }
  }, [isStreaming]);

  return { messages, isStreaming, sendMessage, clearMessages } as const;
}
