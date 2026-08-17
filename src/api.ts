/**
 * Backend API (EdgeOne Makers)
 *
 * Route mapping (file → route):
 *   agents/digital-human/index.py          → POST /chat          Main chat endpoint (SSE)
 *   cloud-functions/stop/index.py          → POST /stop          Abort the active agent run
 *   cloud-functions/history/index.ts       → POST /history       Get conversation history
 *   cloud-functions/conversations/index.ts → POST /conversations List conversations
 *   cloud-functions/clear-history/index.ts → POST /clear-history Clear messages
 *   cloud-functions/delete-conversation/index.ts → POST /delete-conversation
 */

import type { Message, ListConversationsParams, ListConversationsResponse } from './types';

export const API = {
  chat: '/chat',
  chatStop: '/stop',
  history: '/history',
  clearHistory: '/clear-history',
  conversations: '/conversations',
  deleteConversation: '/delete-conversation',
} as const;

export interface RawSseEvent {
  eventType: string;
  data: unknown;
  raw: string;
  timestamp: number;
}

export interface StreamCallbacks {
  onTextDelta: (delta: string) => void;
  onToolCalled: (toolName: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
  onRawEvent?: (event: RawSseEvent) => void;
}

export async function fetchConversationHistory(
  conversationId: string,
  userId?: string,
): Promise<Message[]> {
  try {
    const res = await fetch(API.history, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    if (!res.ok) return [];
    const data = await res.json().catch(() => null) as { messages?: Message[] } | null;
    return Array.isArray(data?.messages) ? data.messages : [];
  } catch {
    return [];
  }
}

export function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  conversationId?: string,
  options?: { userId?: string; userMsgId?: string; botMsgId?: string },
): AbortController {
  const ctrl = new AbortController();

  (async () => {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (conversationId) {
        headers['makers-conversation-id'] = conversationId;
      }

      const res = await fetch(API.chat, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message, ...options }),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        callbacks.onError(new Error(`HTTP ${res.status}: ${await res.text().catch(() => '')}`));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError(new Error('ReadableStream not supported'));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let doneReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          if (!part.trim()) continue;
          dispatchSseChunk(part, callbacks, () => { doneReceived = true; });
        }
      }

      if (!doneReceived) callbacks.onDone();
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      callbacks.onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return ctrl;
}

function dispatchSseChunk(part: string, cb: StreamCallbacks, markDone: () => void): void {
  let eventType = '';
  let data = '';

  for (const line of part.split('\n')) {
    if (line.startsWith('event: ')) eventType = line.slice(7);
    else if (line.startsWith('data: ')) data = line.slice(6);
  }

  if (!eventType || !data) return;

  try {
    const parsed = JSON.parse(data);
    if (cb.onRawEvent) cb.onRawEvent({ eventType, data: parsed, raw: data, timestamp: Date.now() });

    switch (eventType) {
      case 'text_delta':
        cb.onTextDelta(parsed.delta);
        break;
      case 'tool_called':
        cb.onToolCalled(parsed.tool);
        break;
      case 'error':
        cb.onError(new Error(parsed.message || 'agent returned error'));
        break;
      case 'done':
        markDone();
        cb.onDone();
        break;
    }
  } catch {
    if (cb.onRawEvent) cb.onRawEvent({ eventType, data: null, raw: data, timestamp: Date.now() });
  }
}

export async function stopAgent(conversationId?: string): Promise<boolean> {
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (conversationId) headers['makers-conversation-id'] = conversationId;
    const res = await fetch(API.chatStop, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function clearConversationHistory(conversationId?: string, userId?: string): Promise<boolean> {
  if (!conversationId) return false;
  try {
    const res = await fetch(API.clearHistory, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function listConversations(params: ListConversationsParams): Promise<ListConversationsResponse> {
  try {
    const res = await fetch(API.conversations, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!res.ok) return { conversations: [] };
    const data = await res.json().catch(() => null) as ListConversationsResponse | null;
    return data || { conversations: [] };
  } catch {
    return { conversations: [] };
  }
}

export async function deleteConversation(conversationId: string, userId?: string): Promise<boolean> {
  if (!conversationId) return false;
  try {
    const res = await fetch(API.deleteConversation, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
