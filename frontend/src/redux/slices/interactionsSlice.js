import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/client";

export const fetchInteractions = createAsyncThunk(
  "interactions/fetchAll",
  async (hcpId) => {
    const res = await api.get("/api/interactions", {
      params: hcpId ? { hcp_id: hcpId } : {},
    });
    return res.data;
  }
);

export const submitInteractionForm = createAsyncThunk(
  "interactions/submitForm",
  async (payload) => {
    const res = await api.post("/api/interactions", payload);
    return res.data;
  }
);

// Kept for the manual "type an edit instruction into the small inline input" path in
// InteractionHistory that doesn't go through the LLM (e.g. a plain field patch payload).
export const editInteraction = createAsyncThunk(
  "interactions/edit",
  async ({ interactionId, updates }) => {
    const res = await api.patch(`/api/interactions/${interactionId}`, updates);
    return res.data;
  }
);

// Search - talks directly to a REST search endpoint for non-chat filter UI (e.g. a
// sentiment dropdown), separate from the chat-driven search_interactions_tool path.
export const searchInteractions = createAsyncThunk(
  "interactions/search",
  async (filters) => {
    const res = await api.get("/api/interactions/search", { params: filters });
    return res.data;
  }
);

const interactionsSlice = createSlice({
  name: "interactions",
  initialState: {
    items: [],
    status: "idle",
    error: null,
    lastSubmitStatus: "idle", // for showing a success/error toast on the form
    // Fields extracted by the chat agent from a "log interaction" message, waiting to be
    // reviewed and confirmed in the structured form. Nothing is saved to the DB until the
    // rep submits the form themselves.
    draft: null,
    // Results from search_interactions_tool (chat-driven) or searchInteractions (REST),
    // shown in a dedicated results panel rather than mixed into the main history list.
    searchResults: [],
    searchStatus: "idle",
  },
  reducers: {
    resetSubmitStatus(state) {
      state.lastSubmitStatus = "idle";
    },
    setDraft(state, action) {
      state.draft = action.payload;
    },
    clearDraft(state) {
      state.draft = null;
    },
    // Applied when edit_interaction_tool commits via the chat/edit-prompt path, so the
    // list reflects the change immediately without waiting on a refetch round-trip.
    applyEditResult(state, action) {
      const { interaction_id, applied_changes } = action.payload;
      const idx = state.items.findIndex((i) => i.id === interaction_id);
      if (idx === -1 || !applied_changes) return;
      const item = state.items[idx];
      if ("notes" in applied_changes) item.notes = applied_changes.notes;
      if ("summary" in applied_changes) item.summary = applied_changes.summary;
      if ("sentiment" in applied_changes) item.sentiment = applied_changes.sentiment;
      if ("samples_provided" in applied_changes) item.samples_provided = JSON.stringify(applied_changes.samples_provided);
      if ("materials_shared" in applied_changes) item.materials_shared = JSON.stringify(applied_changes.materials_shared);
      if ("outcomes" in applied_changes) item.outcomes = applied_changes.outcomes;
      if ("follow_up_actions" in applied_changes) item.follow_up_actions = applied_changes.follow_up_actions;
    },
    clearSearchResults(state) {
      state.searchResults = [];
      state.searchStatus = "idle";
    },
    // Populated when search_interactions_tool returns results via the chat panel.
    setSearchResultsFromChat(state, action) {
      state.searchResults = action.payload.results || [];
      state.searchStatus = "succeeded";
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchInteractions.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchInteractions.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchInteractions.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message;
      })
      .addCase(submitInteractionForm.pending, (state) => {
        state.lastSubmitStatus = "loading";
      })
      .addCase(submitInteractionForm.fulfilled, (state, action) => {
        state.lastSubmitStatus = "succeeded";
        state.items.unshift(action.payload);
        state.draft = null; // clear the draft once it's actually been logged
      })
      .addCase(submitInteractionForm.rejected, (state, action) => {
        state.lastSubmitStatus = "failed";
        state.error = action.error.message;
      })
      .addCase(editInteraction.fulfilled, (state, action) => {
        const idx = state.items.findIndex((i) => i.id === action.payload.id);
        if (idx !== -1) state.items[idx] = action.payload;
      })
      .addCase(searchInteractions.pending, (state) => {
        state.searchStatus = "loading";
      })
      .addCase(searchInteractions.fulfilled, (state, action) => {
        state.searchStatus = "succeeded";
        state.searchResults = action.payload;
      })
      .addCase(searchInteractions.rejected, (state, action) => {
        state.searchStatus = "failed";
        state.error = action.error.message;
      });
  },
});

export const {
  resetSubmitStatus,
  setDraft,
  clearDraft,
  applyEditResult,
  clearSearchResults,
  setSearchResultsFromChat,
} = interactionsSlice.actions;
export default interactionsSlice.reducer;