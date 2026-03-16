/** Chat interface — message list, input, and profile completion sidebar. */

import { useEffect, useRef, useState } from 'react';
import { useChat } from '../../hooks/useChat';
import { ChatMessage } from './ChatMessage';
import { CompletionIndicator } from '../common/CompletionIndicator';

/** Chat state that can be owned by a parent to survive unmount/remount cycles. */
export type ChatState = ReturnType<typeof useChat>;

interface Props {
  onProfileUpdated?: () => void;
  /** If provided, use this external chat state instead of creating a new one. */
  chatState?: ChatState;
}

export function ChatInterface({ onProfileUpdated, chatState }: Props) {
  const ownChat = useChat();
  const { messages, sending, error, completionPct, send, reset } = chatState ?? ownChat;
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Notify parent when profile is updated
  useEffect(() => {
    if (messages.length > 0) {
      const last = messages[messages.length - 1];
      if (last.extractedFields && last.extractedFields.length > 0 && onProfileUpdated) {
        onProfileUpdated();
      }
    }
  }, [messages, onProfileUpdated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || sending) return;
    const msg = input;
    setInput('');
    await send(msg);
    inputRef.current?.focus();
  };

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <div className="chat-header-left">
          <h3>JGP Profile Assistant</h3>
          <span className="chat-subtitle">AI-powered profile builder</span>
        </div>
        <div className="chat-header-right">
          <CompletionIndicator percentage={completionPct} size="sm" />
          <button className="btn-link btn-sm" onClick={reset}>New Chat</button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <p>Hi! I'm your JGP Profile Assistant.</p>
            <p>Tell me about yourself and I'll help fill out your profile. You can say things like:</p>
            <div className="chat-suggestions">
              <button className="chat-suggestion" onClick={() => send("I'm a real estate agent in Denver, CO")}>
                "I'm a real estate agent in Denver, CO"
              </button>
              <button className="chat-suggestion" onClick={() => send("I'm a first-time home buyer looking to purchase in the $400-500k range")}>
                "I'm a first-time home buyer..."
              </button>
              <button className="chat-suggestion" onClick={() => send("I'm a loan officer at Summit National Bank")}>
                "I'm a loan officer at..."
              </button>
            </div>
          </div>
        )}

        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {sending && (
          <div className="chat-message chat-assistant">
            <div className="chat-bubble chat-typing">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}

        {error && (
          <div className="chat-error">{error}</div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={sending}
          autoFocus
        />
        <button type="submit" className="btn-primary" disabled={sending || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
