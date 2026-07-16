import React, { useState, useRef, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { sendChatMessage } from "../redux/slices/chatSlice";
import { fetchInteractions } from "../redux/slices/interactionsSlice";
import "./ChatInterface.css";

export default function ChatInterface() {
  const dispatch = useDispatch();
  const { messages, status } = useSelector((state) => state.chat);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const hasConversation = messages.length > 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const message = input.trim();
    if (!message || status === "loading") return;
    setInput("");
    await dispatch(sendChatMessage({ message }));
    // Refreshes the interaction list, which matters for tools that commit immediately
    // (edit_interaction, etc). Log-interaction messages only populate the form draft
    // and don't create a row until the rep submits, so this is a harmless no-op for those.
    dispatch(fetchInteractions());
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="assistant-panel card">
      <div className="assistant-panel__header">
        <div className="assistant-panel__title">🤖 AI Assistant</div>
        <div className="assistant-panel__subtitle">Describe a visit and I'll fill in the form for you</div>
      </div>

      <div className="assistant-panel__body">
        {!hasConversation ? (
          <div className="assistant-panel__placeholder">
            Try: "Met Dr. Rao, discussed Cardexil efficacy, positive sentiment, gave 2
            samples" — I'll fill in the form on the left so you can review before saving.
            You can also ask me to look up an HCP, schedule a follow-up, or flag an
            adverse event.
          </div>
        ) : (
          <div className="assistant-panel__messages">
            {messages.map((m, i) => (
              <ChatBubble key={i} message={m} />
            ))}
            {status === "loading" && (
              <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                <span className="dot" /><span className="dot" /><span className="dot" />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="assistant-panel__input-row">
        <input
          type="text"
          placeholder="Describe interaction..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className="btn btn--primary"
          onClick={handleSend}
          disabled={status === "loading" || !input.trim()}
        >
          ⚡ Send
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-bubble ${isUser ? "chat-bubble--user" : "chat-bubble--assistant"}`}>
      <div className="chat-bubble__text">{message.text}</div>
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="chat-bubble__tool-tag">⚙ {message.toolCalls.join(", ")}</div>
      )}
    </div>
  );
}