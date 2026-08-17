import { useState, useCallback, useEffect, useRef } from 'react';
import type { Message } from './types';
import { fetchConversationHistory, sendMessageStream, stopAgent } from './api';
import styles from './App.module.css';

const LAMP_IDS = ['generate_script', 'analyze_script', 'generate_cover_image', 'call_digital_human'] as const;
const LAMP_ICONS: Record<string, string> = {
  generate_script: '✍️',
  analyze_script: '📝',
  generate_cover_image: '🖼️',
  call_digital_human: '🎬',
};
const LAMP_LABELS: Record<string, string> = {
  generate_script: '生成文案',
  analyze_script: '分析标题',
  generate_cover_image: '生成封面',
  call_digital_human: '生成视频',
};

const CONVERSATION_ID_STORAGE_KEY = 'ip_conversation_id';
const EO_USER_ID_STORAGE_KEY = 'ip-uuid';

function getExistingConversationId(): string | null {
  return localStorage.getItem(CONVERSATION_ID_STORAGE_KEY);
}

function getOrCreateConversationId(): string {
  const cached = getExistingConversationId();
  if (cached) return cached;
  const id = crypto.randomUUID();
  localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, id);
  return id;
}

function getOrCreateUuid(): string {
  const cached = localStorage.getItem(EO_USER_ID_STORAGE_KEY);
  if (cached) return cached;
  const id = crypto.randomUUID();
  localStorage.setItem(EO_USER_ID_STORAGE_KEY, id);
  return id;
}

const hadExistingConversationIdRef = { current: getExistingConversationId() !== null };

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [lamps, setLamps] = useState<{id: string; label: string; icon: string; active: boolean; animKey: number}[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [activeConversationId, setActiveConversationId] = useState<string>(() => getOrCreateConversationId());
  const botMsgIdRef = useRef<string>('');
  const abortCtrlRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string>(activeConversationId);
  const eoUuidRef = useRef<string>(getOrCreateUuid());

  useEffect(() => {
    setLamps(LAMP_IDS.map(id => ({
      id,
      label: LAMP_LABELS[id],
      icon: LAMP_ICONS[id],
      active: false,
      animKey: 0,
    })));
  }, []);

  useEffect(() => {
    conversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  const updateBotMessage = useCallback((updater: (content: string) => string) => {
    setMessages(prev => prev.map(m =>
      m.id === botMsgIdRef.current ? { ...m, content: updater(m.content) } : m
    ));
  }, []);

  const clearBotStreaming = useCallback(() => {
    setMessages(prev => {
      let changed = false;
      const next = prev.map(m => {
        if (m.id === botMsgIdRef.current && m.streaming) {
          changed = true;
          const { streaming, ...rest } = m;
          return rest;
        }
        return m;
      });
      return changed ? next : prev;
    });
  }, []);

  const finishStream = useCallback(() => {
    setLoading(false);
    abortCtrlRef.current = null;
  }, []);

  const handleSend = useCallback(async (text: string) => {
    setDebugEvents([]);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    const botMsgId = crypto.randomUUID();
    botMsgIdRef.current = botMsgId;
    const botMsg: Message = {
      id: botMsgId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      streaming: true,
    };

    setMessages(prev => [...prev, userMsg, botMsg]);
    setLoading(true);

    const ctrl = sendMessageStream(text, {
      onTextDelta(delta) {
        updateBotMessage(content => content + delta);
      },
      onToolCalled(toolName) {
        setLamps(prev =>
          prev.map(l =>
            l.id === toolName ? { ...l, active: true, animKey: l.animKey + 1 } : l
          )
        );
        setTimeout(() => {
          setLamps(prev => prev.map(l => l.id === toolName ? { ...l, active: false } : l));
        }, 1500);
      },
      onDone() {
        clearBotStreaming();
        finishStream();
      },
      onError() {
        clearBotStreaming();
        updateBotMessage(content => content || '出错了，请重试');
        finishStream();
      },
    }, conversationIdRef.current, {
      userId: eoUuidRef.current,
    });

    abortCtrlRef.current = ctrl;
  }, [updateBotMessage, clearBotStreaming, finishStream]);

  const [debugEvents, setDebugEvents] = useState<any[]>([]);

  const handleStop = useCallback(() => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
      abortCtrlRef.current = null;
    }
    updateBotMessage(content => content ? content + '\n\n⏹ 已停止' : '⏹ 已停止');
    setLoading(false);
  }, [updateBotMessage]);

  const handleClearHistory = useCallback(() => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
      abortCtrlRef.current = null;
    }
    const newId = crypto.randomUUID();
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, newId);
    conversationIdRef.current = newId;
    setActiveConversationId(newId);
    setMessages([]);
    setDebugEvents([]);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!hadExistingConversationIdRef.current) {
      setHistoryLoading(false);
      return;
    }
    fetchConversationHistory(conversationIdRef.current, eoUuidRef.current)
      .then(hist => {
        if (hist.length > 0) setMessages(hist);
      })
      .finally(() => {
        setHistoryLoading(false);
      });
  }, []);

  return (
    <div className={styles.app}>
      <main className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.title}>个人IP口播助手</h1>
          <p className={styles.subtitle}>输入你的想法，帮你生成口播文案</p>
        </header>
        <ChatWindow messages={messages} loading={loading} />
        <div className={styles.toolLamps}>
          {lamps.map(lamp => (
            <div
              key={lamp.id}
              className={`${styles.lamp} ${lamp.active ? styles.lampActive : ''}`}
              title={lamp.label}
            >
              <span className={styles.lampIcon}>{lamp.icon}</span>
              <span className={styles.lampLabel}>{lamp.label}</span>
            </div>
          ))}
        </div>
        <ChatInput onSend={handleSend} onStop={handleStop} loading={loading} />
      </main>
    </div>
  );
}

// ---- Sub components (inline for simplicity) ----

function ChatWindow({ messages, loading }: { messages: Message[]; loading: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  return (
    <div className={styles.chatWindow}>
      {messages.map(m => (
        <div key={m.id} className={m.role === 'user' ? styles.userMsg : styles.botMsg}>
          <div className={styles.msgBubble}>{m.content}</div>
        </div>
      ))}
      {loading && <div className={styles.botMsg}><div className={styles.msgBubble + ' ' + styles.loading}>思考中...</div></div>}
      <div ref={endRef} />
    </div>
  );
}

function ChatInput({ onSend, onStop, loading }: { onSend: (text: string) => void; onStop: () => void; loading: boolean }) {
  const [text, setText] = useState('');
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setText('');
  };
  return (
    <form className={styles.chatInput} onSubmit={handleSubmit}>
      <input
        className={styles.input}
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="输入你的想法或主题..."
        disabled={loading}
      />
      <button type="submit" className={styles.sendBtn} disabled={loading || !text.trim()}>
        {loading ? '⏹' : '➤'}
      </button>
    </form>
  );
}
