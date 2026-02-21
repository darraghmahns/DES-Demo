/** Hook for the AI profile builder chatbot. */

import { useCallback, useState } from 'react';
import {
  sendChatMessage,
  type ExtractedField,
} from '../api/chat';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  extractedFields?: ExtractedField[];
  completionBefore?: number;
  completionAfter?: number;
  timestamp: Date;
}

interface UseChatReturn {
  messages: ChatMessage[];
  sessionId: string | null;
  sending: boolean;
  error: string | null;
  completionPct: number;
  send: (message: string) => Promise<void>;
  reset: () => void;
}

let _msgCounter = 0;

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completionPct, setCompletionPct] = useState(0);

  const send = useCallback(async (message: string) => {
    if (!message.trim()) return;

    const userMsg: ChatMessage = {
      id: `msg-${++_msgCounter}`,
      role: 'user',
      content: message,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setSending(true);
    setError(null);

    try {
      const res = await sendChatMessage(message, sessionId || undefined);
      setSessionId(res.session_id);

      const assistantMsg: ChatMessage = {
        id: `msg-${++_msgCounter}`,
        role: 'assistant',
        content: res.reply,
        extractedFields: res.extracted_fields,
        completionBefore: res.completion_before,
        completionAfter: res.completion_after,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMsg]);
      setCompletionPct(res.completion_after);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  }, [sessionId]);

  const reset = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setError(null);
    setCompletionPct(0);
  }, []);

  return { messages, sessionId, sending, error, completionPct, send, reset };
}
