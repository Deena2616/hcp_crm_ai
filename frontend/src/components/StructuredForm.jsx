import React, { useState, useEffect, useRef, useCallback } from "react";
import { useDispatch, useSelector } from "react-redux";
import { submitInteractionForm, resetSubmitStatus, fetchInteractions, clearDraft } from "../redux/slices/interactionsSlice";
import HcpAutocomplete from "./HcpAutocomplete";
import api from "../api/client";
import "../styles/StructuredForm.css";

const INTERACTION_TYPES = [
  { value: "meeting", label: "Meeting" },
  { value: "call", label: "Call" },
  { value: "video_call", label: "Video Call" },
  { value: "email", label: "Email" },
  { value: "conference", label: "Conference" },
];

function nowDateStr() {
  return new Date().toISOString().slice(0, 10);
}
function nowTimeStr() {
  return new Date().toTimeString().slice(0, 5);
}

export default function StructuredForm() {
  const dispatch = useDispatch();
  const { lastSubmitStatus, draft } = useSelector((state) => state.interactions);

  const [hcpName, setHcpName] = useState("");
  const [interactionType, setInteractionType] = useState("meeting");
  const [date, setDate] = useState(nowDateStr());
  const [time, setTime] = useState(nowTimeStr());
  const [attendees, setAttendees] = useState("");
  const [notes, setNotes] = useState("");
  const [sentiment, setSentiment] = useState("neutral");
  const [outcomes, setOutcomes] = useState("");
  const [followUpActions, setFollowUpActions] = useState("");

  const [materials, setMaterials] = useState([]);
  const [samples, setSamples] = useState([]);
  const [addingMaterial, setAddingMaterial] = useState(false);
  const [addingSample, setAddingSample] = useState(false);
  const [materialInput, setMaterialInput] = useState("");
  const [sampleInput, setSampleInput] = useState("");

  const [showVoiceNote, setShowVoiceNote] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [voiceLoading, setVoiceLoading] = useState(false);

  const [justFilledByAI, setJustFilledByAI] = useState(false);

  const [suggestions, setSuggestions] = useState([]);
  const suggestTimer = useRef(null);

  // When the chat agent produces a log_interaction draft, MERGE it into the form fields
  // rather than replacing them - so describing a visit across a couple of chat messages
  // (or manually tweaking a field, then adding more via chat) progressively builds up the
  // same draft instead of each new message wiping out the last. Nothing is saved to the
  // database until the rep clicks "Log Interaction".
  useEffect(() => {
    if (!draft) return;

    // hcp name / interaction type: take the latest chat value if it provided one, since a
    // rep correcting "actually it was Dr. Mehta, not Dr. Rao" mid-conversation should win.
    setHcpName((prev) => draft.hcp_name || prev);
    setInteractionType((prev) => draft.interaction_type || prev);

    // date/time: only overwrite if THIS message actually mentioned a date/time. Otherwise
    // keep whatever is already in the form (don't reset to "now" on every draft).
    if (draft.occurred_date) setDate(draft.occurred_date);
    if (draft.occurred_time) setTime(draft.occurred_time);

    // free-text fields: accumulate rather than replace, skipping exact duplicates so
    // re-renders of the same draft don't double up the text.
    const appendUnique = (prev, addition) => {
      if (!addition) return prev;
      if (!prev) return addition;
      if (prev.includes(addition)) return prev;
      return `${prev}\n${addition}`;
    };
    setNotes((prev) => appendUnique(prev, draft.notes || draft.summary || ""));
    setOutcomes((prev) => appendUnique(prev, draft.outcomes || ""));
    setFollowUpActions((prev) => appendUnique(prev, draft.follow_up_actions || ""));

    // sentiment: take the latest read, since a later message often refines/corrects it.
    setSentiment(draft.sentiment || "neutral");

    // lists: union with what's already there instead of replacing.
    setMaterials((prev) => Array.from(new Set([...prev, ...(draft.materials_shared || [])])));
    setSamples((prev) => Array.from(new Set([...prev, ...(draft.samples_provided || [])])));

    setJustFilledByAI(true);
    const t = setTimeout(() => setJustFilledByAI(false), 3000);
    return () => clearTimeout(t);
  }, [draft]);

  useEffect(() => {
    if (lastSubmitStatus === "succeeded") {
      setHcpName("");
      setNotes("");
      setOutcomes("");
      setFollowUpActions("");
      setAttendees("");
      setMaterials([]);
      setSamples([]);
      setSuggestions([]);
      setSentiment("neutral");
      const t = setTimeout(() => dispatch(resetSubmitStatus()), 2500);
      return () => clearTimeout(t);
    }
  }, [lastSubmitStatus, dispatch]);

  const triggerSuggestions = useCallback((nextNotes, nextOutcomes) => {
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    suggestTimer.current = setTimeout(async () => {
      if (!nextNotes && !nextOutcomes) return;
      try {
        const res = await api.post("/api/assist/suggest-followups", {
          hcp_name: hcpName || null,
          notes: nextNotes,
          outcomes: nextOutcomes,
        });
        setSuggestions(res.data.suggestions || []);
      } catch {
        // silent - suggestions are a nice-to-have
      }
    }, 900);
  }, [hcpName]);

  const handleNotesBlur = () => triggerSuggestions(notes, outcomes);
  const handleOutcomesBlur = () => triggerSuggestions(notes, outcomes);

  const applySuggestion = (s) => {
    setFollowUpActions((prev) => (prev ? `${prev}\n${s}` : s));
    setSuggestions((prev) => prev.filter((x) => x !== s));
  };

  const handleSummarizeVoiceNote = async () => {
    if (!transcript.trim()) return;
    setVoiceLoading(true);
    try {
      const res = await api.post("/api/assist/summarize-voice-note", { transcript: transcript.trim() });
      setNotes((prev) => (prev ? `${prev}\n${res.data.notes}` : res.data.notes));
      setOutcomes((prev) => (prev ? `${prev}\n${res.data.outcomes}` : res.data.outcomes));
      setShowVoiceNote(false);
      setTranscript("");
    } catch {
      // no-op; keep the panel open so they can retry
    } finally {
      setVoiceLoading(false);
    }
  };

  const addMaterial = () => {
    if (!materialInput.trim()) return;
    setMaterials((prev) => [...prev, materialInput.trim()]);
    setMaterialInput("");
    setAddingMaterial(false);
  };

  const addSample = () => {
    if (!sampleInput.trim()) return;
    setSamples((prev) => [...prev, sampleInput.trim()]);
    setSampleInput("");
    setAddingSample(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!hcpName.trim()) return;

    const occurredAt = date && time ? new Date(`${date}T${time}:00`).toISOString() : undefined;

    await dispatch(submitInteractionForm({
      hcp_name: hcpName.trim(),
      interaction_type: interactionType,
      occurred_at: occurredAt,
      attendees: attendees.split(",").map((a) => a.trim()).filter(Boolean),
      notes,
      materials_shared: materials,
      samples_provided: samples,
      sentiment,
      outcomes,
      follow_up_actions: followUpActions,
      source: draft ? "chat" : "form",
    }));
    dispatch(clearDraft());
    dispatch(fetchInteractions());
  };

  return (
    <form className="form-panel card" onSubmit={handleSubmit}>
      <div className="form-panel__scroll">
        <h2 className="form-panel__title">Log HCP Interaction</h2>

        {justFilledByAI && (
          <div className="form-panel__ai-banner">
            ✨ Filled in from your chat message — review and click Log Interaction to save.
          </div>
        )}

        <div className="form-grid">
          <label>
            HCP Name
            <HcpAutocomplete value={hcpName} onChange={setHcpName} />
          </label>
          <label>
            Interaction Type
            <select value={interactionType} onChange={(e) => setInteractionType(e.target.value)}>
              {INTERACTION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="form-grid">
          <label>
            Date
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Time
            <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </label>
        </div>

        <label>
          Attendees
          <input
            value={attendees}
            onChange={(e) => setAttendees(e.target.value)}
            placeholder="Enter names or search..."
          />
        </label>

        <label>
          Topics Discussed
          <textarea
            rows={4}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={handleNotesBlur}
            placeholder="Enter key discussion points..."
          />
        </label>

        {!showVoiceNote ? (
          <button type="button" className="link-btn" onClick={() => setShowVoiceNote(true)}>
            🎙 Summarize from Voice Note (Requires Consent)
          </button>
        ) : (
          <div className="voice-note-box">
            <textarea
              rows={3}
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="Paste the voice note transcript here — the AI will turn it into Topics Discussed and Outcomes..."
            />
            <div className="voice-note-box__actions">
              <button
                type="button"
                className="btn btn--primary btn--sm"
                onClick={handleSummarizeVoiceNote}
                disabled={voiceLoading || !transcript.trim()}
              >
                {voiceLoading ? "Summarizing..." : "Summarize"}
              </button>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => setShowVoiceNote(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="materials-row">
          <div className="materials-col">
            <span className="materials-col__label">Materials Shared</span>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAddingMaterial(true)}>
              🔍 Search/Add
            </button>
            {addingMaterial && (
              <div className="inline-add">
                <input
                  autoFocus
                  value={materialInput}
                  onChange={(e) => setMaterialInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addMaterial())}
                  placeholder="Material name"
                />
                <button type="button" className="btn btn--primary btn--sm" onClick={addMaterial}>Add</button>
              </div>
            )}
            <div className="chip-list">
              {materials.length === 0 && <span className="chip-list__empty">No materials added</span>}
              {materials.map((m) => (
                <span key={m} className="chip">
                  {m}
                  <button type="button" onClick={() => setMaterials(materials.filter((x) => x !== m))}>×</button>
                </span>
              ))}
            </div>
          </div>

          <div className="materials-col">
            <span className="materials-col__label">Samples Distributed</span>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAddingSample(true)}>
              💊 Add Sample
            </button>
            {addingSample && (
              <div className="inline-add">
                <input
                  autoFocus
                  value={sampleInput}
                  onChange={(e) => setSampleInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSample())}
                  placeholder="Sample name"
                />
                <button type="button" className="btn btn--primary btn--sm" onClick={addSample}>Add</button>
              </div>
            )}
            <div className="chip-list">
              {samples.length === 0 && <span className="chip-list__empty">No samples added</span>}
              {samples.map((s) => (
                <span key={s} className="chip">
                  {s}
                  <button type="button" onClick={() => setSamples(samples.filter((x) => x !== s))}>×</button>
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="sentiment-block">
          <span className="sentiment-block__label">Observed/Inferred HCP Sentiment</span>
          <div className="sentiment-block__options">
            {["positive", "neutral", "negative"].map((s) => (
              <label key={s} className="radio-inline">
                <input
                  type="radio"
                  name="sentiment"
                  value={s}
                  checked={sentiment === s}
                  onChange={() => setSentiment(s)}
                />
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </label>
            ))}
          </div>
        </div>

        <label>
          Outcomes
          <textarea
            rows={2}
            value={outcomes}
            onChange={(e) => setOutcomes(e.target.value)}
            onBlur={handleOutcomesBlur}
            placeholder="Key outcomes or agreements..."
          />
        </label>

        <label>
          Follow-up Actions
          <textarea
            rows={2}
            value={followUpActions}
            onChange={(e) => setFollowUpActions(e.target.value)}
            placeholder="Enter next steps or tasks..."
          />
        </label>

        {suggestions.length > 0 && (
          <div className="ai-suggestions">
            <span className="ai-suggestions__label">AI Suggested Follow-ups:</span>
            {suggestions.map((s) => (
              <button key={s} type="button" className="ai-suggestions__item" onClick={() => applySuggestion(s)}>
                + {s}
              </button>
            ))}
          </div>
        )}

        <button
          type="submit"
          className="btn btn--primary form-panel__submit"
          disabled={lastSubmitStatus === "loading" || !hcpName.trim()}
        >
          {lastSubmitStatus === "loading" ? "Logging..." : "Log Interaction"}
        </button>
        {lastSubmitStatus === "succeeded" && (
          <span className="form-panel__success">✓ Interaction logged</span>
        )}
        {lastSubmitStatus === "failed" && (
          <span className="form-panel__error">Something went wrong. Try again.</span>
        )}
      </div>
    </form>
  );
}