/** Single chat message bubble — user or assistant. */

import type { ChatMessage as ChatMsg } from '../../hooks/useChat';

interface Props {
  message: ChatMsg;
}

export function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div className={`chat-message ${isUser ? 'chat-user' : 'chat-assistant'}`}>
      <div className="chat-bubble">
        <div className="chat-content">{message.content}</div>

        {message.extractedFields && message.extractedFields.length > 0 && (
          <div className="chat-extracted">
            <span className="extracted-label">Updated fields:</span>
            {message.extractedFields.map((f, i) => (
              <span key={i} className="extracted-chip">
                {f.field}: {f.value}
              </span>
            ))}
          </div>
        )}

        {message.completionBefore !== undefined &&
          message.completionAfter !== undefined &&
          message.completionAfter > message.completionBefore && (
            <div className="chat-completion-bump">
              Profile: {Math.round(message.completionBefore)}% to {Math.round(message.completionAfter)}%
            </div>
          )}
      </div>
    </div>
  );
}
