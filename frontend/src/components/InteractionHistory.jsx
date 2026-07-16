import React, { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fetchInteractions } from "../redux/slices/interactionsSlice";
import { sendEditMessage } from "../redux/slices/chatSlice";
import "../styles/InteractionHistory.css";

const TYPE_LABELS = {
  meeting: "Meeting",
  call: "Call",
  video_call: "Video Call",
  email: "Email",
  conference: "Conference",
};

export default function InteractionHistory() {
  const dispatch = useDispatch();
  const { items, status } = useSelector((state) => state.interactions);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState(null);

  useEffect(() => {
    dispatch(fetchInteractions());
  }, [dispatch]);

  const startEdit = (id) => {
    setEditingId(id);
    setEditText("");
    setEditError(null);
  };

  const submitEdit = async (interactionId, hcpName) => {
    if (!editText.trim() || editSubmitting) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      const res = await dispatch(
        sendEditMessage({ message: editText.trim(), interactionId, hcpName })
      ).unwrap();
      if (res.data?.status === "updated" || res.tool_calls?.includes("edit_interaction_tool")) {
        setEditingId(null);
        setEditText("");
      } else {
        setEditError(res.reply || "Couldn't apply that edit — try rephrasing.");
      }
    } catch (e) {
      setEditError("Something went wrong applying that edit. Please try again.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const parseList = (raw) => {
    try { return JSON.parse(raw || "[]"); } catch { return []; }
  };

  return (
    <section className="history">
      <div className="history__header">
        <h2 className="history__title">Interaction History</h2>
        <span className="history__count">{items.length} logged</span>
      </div>

      {status === "loading" && (
        <div className="history__state-container">
          <div className="history__loader"></div>
          <div className="history__hint">Loading interactions...</div>
        </div>
      )}
      
      {status === "succeeded" && items.length === 0 && (
        <div className="history__state-container">
          <div className="history__hint">No interactions logged yet.</div>
        </div>
      )}

      <div className="history__list">
        {items.map((item) => {
          const attendees = parseList(item.attendees);
          const materials = parseList(item.materials_shared);
          const samples = parseList(item.samples_provided);

          return (
            <div className="history-item card" key={item.id}>
              <div className="history-item__top">
                <span className={`tag tag--${item.sentiment || 'neutral'}`}>
                  {item.sentiment}
                </span>
                <span className="history-item__type">
                  {TYPE_LABELS[item.interaction_type] || item.interaction_type}
                </span>
                <span className="history-item__source">via {item.source}</span>
                <span className="history-item__date">
                  {new Date(item.occurred_at).toLocaleString([], {
                    dateStyle: 'medium',
                    timeStyle: 'short'
                  })}
                </span>
              </div>

              {attendees.length > 0 && (
                <div className="history-item__attendees">
                  <strong>Attendees:</strong> {attendees.join(", ")}
                </div>
              )}

              <p className="history-item__notes">{item.summary || item.notes}</p>

              {item.outcomes && (
                <p className="history-item__field">
                  <strong>Outcomes:</strong> {item.outcomes}
                </p>
              )}
              {item.follow_up_actions && (
                <p className="history-item__field">
                  <strong>Follow-up:</strong> {item.follow_up_actions}
                </p>
              )}

              {(materials.length > 0 || samples.length > 0) && (
                <div className="history-item__chips">
                  {materials.map((m) => (
                    <span key={m} className="history-item__chip history-item__chip--material">
                      📄 {m}
                    </span>
                  ))}
                  {samples.map((s) => (
                    <span key={s} className="history-item__chip history-item__chip--sample">
                      💊 {s}
                    </span>
                  ))}
                </div>
              )}

              {editingId === item.id ? (
                <div className="history-item__edit-area">
                  <div className="history-item__edit-row">
                    <input
                      autoFocus
                      placeholder='e.g. "change sentiment to negative" or "add DrugX to samples"'
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && submitEdit(item.id, item.hcp_name)}
                      disabled={editSubmitting}
                    />
                    <button
                      className="btn btn--primary btn--sm"
                      onClick={() => submitEdit(item.id, item.hcp_name)}
                      disabled={editSubmitting || !editText.trim()}
                    >
                      {editSubmitting ? "Applying..." : "Apply"}
                    </button>
                    <button 
                      className="btn btn--ghost btn--sm" 
                      onClick={() => setEditingId(null)} 
                      disabled={editSubmitting}
                    >
                      Cancel
                    </button>
                  </div>
                  {editError && <div className="history-item__edit-error">{editError}</div>}
                </div>
              ) : (
                <button className="history-item__edit-btn" onClick={() => startEdit(item.id)}>
                  ✏️ Edit this entry
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}