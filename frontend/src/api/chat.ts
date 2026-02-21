/** Chat API functions for D.E.S. Profile Builder Chatbot. */

import { apiFetch } from './client';

export interface ExtractedField {
  field: string;
  value: string;
  section: string;
}

export interface ChatResponse {
  reply: string;
  session_id: string;
  extracted_fields: ExtractedField[];
  profile_updated: boolean;
  completion_before: number;
  completion_after: number;
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatHistoryResponse {
  session_id: string | null;
  messages: ChatHistoryMessage[];
}

export async function sendChatMessage(
  message: string,
  sessionId?: string,
): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/api/profile/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      session_id: sessionId || undefined,
    }),
  });
}

export async function getChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
  return apiFetch<ChatHistoryResponse>(`/api/profile/chat/history?session_id=${sessionId}`);
}
