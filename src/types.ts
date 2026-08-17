export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  streaming?: boolean;
}

export interface ListConversationsParams {
  userId: string;
  limit?: number;
  order?: 'asc' | 'desc';
  after?: string;
  before?: string;
}

export interface ListConversationsResponse {
  conversations: Array<{
    id: string;
    lastMessageAt: number;
    messageCount: number;
  }>;
  nextCursor?: string;
  previousCursor?: string;
}
