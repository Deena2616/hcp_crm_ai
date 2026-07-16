import React, { useState, useRef, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { sendChatMessage } from "../redux/slices/chatSlice";
import { fetchInteractions, setSearchResultsFromChat } from "../redux/slices/interactionsSlice";
import "../styles/ChatInterface.css";

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
    const result = await dispatch(sendChatMessage({ message })).unwrap().catch(() => null);

    // Refreshes the interaction list, which matters for tools that commit immediately
    // (edit_interaction_tool, schedule_followup_tool). Log-interaction messages only
    // populate the form draft and don't create a row until the rep submits, so this is a
    // harmless no-op for those.
    dispatch(fetchInteractions());

    // search_interactions_tool results get surfaced in a dedicated results panel rather
    // than mixed into the main history list.
    if (result?.tool_calls?.includes("search_interactions_tool") && result.data?.results) {
      dispatch(setSearchResultsFromChat(result.data));
    }
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
            You can also ask me to edit a past entry ("change the sentiment to negative"),
            schedule a follow-up ("follow up with Dr. Rao in 5 days"), search past visits
            ("show me all positive interactions"), or look up an HCP's profile.
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
          placeholder="Describe interaction, ask to edit, schedule a follow-up, or search..."
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
  const searchResults = message.toolCalls?.includes("search_interactions_tool")
    ? message.data?.results
    : null;

  return (
    <div className={`chat-bubble ${isUser ? "chat-bubble--user" : "chat-bubble--assistant"}`}>
      <div className="chat-bubble__text">{message.text}</div>
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="chat-bubble__tool-tag">⚙ {message.toolCalls.join(", ")}</div>
      )}
      {searchResults && searchResults.length > 0 && (
        <div className="chat-bubble__search-results">
          {searchResults.map((r) => (
            <div key={r.id} className="chat-bubble__search-result">
              <span className={`tag tag--${r.sentiment}`}>{r.sentiment}</span>
              <span className="chat-bubble__search-result-hcp">{r.hcp_name}</span>
              <span className="chat-bubble__search-result-date">
                {new Date(r.date).toLocaleDateString()}
              </span>
              <p className="chat-bubble__search-result-summary">{r.summary}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}