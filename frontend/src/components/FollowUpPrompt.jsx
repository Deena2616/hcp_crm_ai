import React, { useState } from "react";
import { useDispatch } from "react-redux";
import { sendFollowUpMessage } from "../redux/slices/chatSlice";
import "../styles/FollowUpPrompt.css";

/**
 * Dedicated "Schedule follow-up" prompt area, scoped to a specific HCP (e.g. shown on an
 * HCP profile view or next to the structured form). Sends straight to
 * schedule_followup_tool via /api/chat/followup and commits immediately - no draft step,
 * matching how a follow-up request typed into the main chat panel behaves.
 */
export default function FollowUpPrompt({ hcpName }) {
  const dispatch = useDispatch();
  const [text, setText] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | succeeded | failed
  const [lastReply, setLastReply] = useState("");

  const handleSubmit = async () => {
    if (!text.trim() || status === "loading") return;
    setStatus("loading");
    try {
      const res = await dispatch(sendFollowUpMessage({ message: text.trim(), hcpName })).unwrap();
      setLastReply(res.reply || "");
      setStatus(res.data?.status === "scheduled" ? "succeeded" : "failed");
      if (res.data?.status === "scheduled") setText("");
    } catch {
      setStatus("failed");
      setLastReply("Something went wrong scheduling that follow-up.");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="followup-prompt card">
      <div className="followup-prompt__title">📅 Schedule Follow-up{hcpName ? ` — ${hcpName}` : ""}</div>
      <div className="followup-prompt__row">
        <input
          type="text"
          placeholder='e.g. "follow up in 5 days to send the trial data"'
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={status === "loading"}
        />
        <button
          className="btn btn--primary btn--sm"
          onClick={handleSubmit}
          disabled={status === "loading" || !text.trim()}
        >
          {status === "loading" ? "Scheduling..." : "Schedule"}
        </button>
      </div>
      {status === "succeeded" && <div className="followup-prompt__success">✓ {lastReply}</div>}
      {status === "failed" && <div className="followup-prompt__error">{lastReply}</div>}
    </div>
  );
}