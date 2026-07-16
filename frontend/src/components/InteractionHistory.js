import React, { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fetchInteractions, editInteraction } from "../redux/slices/interactionsSlice";
import "./InteractionHistory.css";

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

  useEffect(() => {
    dispatch(fetchInteractions());
  }, [dispatch]);

  const startEdit = (id) => {
    setEditingId(id);
    setEditText("");
  };

  const submitEdit = (interactionId) => {
    if (!editText.trim()) return;
    dispatch(editInteraction({ interactionId, updates: { edit_reason: editText.trim() } }));
    setEditingId(null);
    setEditText("");
  };

  const parseList = (raw) => {
    try { return JSON.parse(raw || "[]"); } catch { return []; }
  };

  return (
    <section className="history">
      <div className="history__title">Interaction History</div>

      {status === "loading" && <div className="history__hint">Loading...</div>}
      {status === "succeeded" && items.length === 0 && (
        <div className="history__hint">No interactions logged yet.</div>
      )}

      <div className="history__list">
        {items.map((item) => {
          const attendees = parseList(item.attendees);
          const materials = parseList(item.materials_shared);
          const samples = parseList(item.samples_provided);

          return (
            <div className="history-item card" key={item.id}>
              <div className="history-item__top">
                <span className={`tag tag--${item.sentiment}`}>{item.sentiment}</span>
                <span className="history-item__type">{TYPE_LABELS[item.interaction_type] || item.interaction_type}</span>
                <span className="history-item__source">via {item.source}</span>
                <span className="history-item__date">
                  {new Date(item.occurred_at).toLocaleString()}
                </span>
              </div>

              {attendees.length > 0 && (
                <div className="history-item__attendees">Attendees: {attendees.join(", ")}</div>
              )}

              <p className="history-item__notes">{item.summary || item.notes}</p>

              {item.outcomes && <p className="history-item__field"><strong>Outcomes:</strong> {item.outcomes}</p>}
              {item.follow_up_actions && (
                <p className="history-item__field"><strong>Follow-up:</strong> {item.follow_up_actions}</p>
              )}

              {(materials.length > 0 || samples.length > 0) && (
                <div className="history-item__chips">
                  {materials.map((m) => <span key={m} className="history-item__chip">📄 {m}</span>)}
                  {samples.map((s) => <span key={s} className="history-item__chip">💊 {s}</span>)}
                </div>
              )}

              {editingId === item.id ? (
                <div className="history-item__edit-row">
                  <input
                    autoFocus
                    placeholder='e.g. "change sentiment to negative" or "add DrugX to samples"'
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && submitEdit(item.id)}
                  />
                  <button className="btn btn--primary btn--sm" onClick={() => submitEdit(item.id)}>Apply</button>
                  <button className="btn btn--ghost btn--sm" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <button className="history-item__edit-btn" onClick={() => startEdit(item.id)}>
                  Edit this entry
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
