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

export const editInteraction = createAsyncThunk(
  "interactions/edit",
  async ({ interactionId, updates }) => {
    const res = await api.patch(`/api/interactions/${interactionId}`, updates);
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
      });
  },
});

export const { resetSubmitStatus, setDraft, clearDraft } = interactionsSlice.actions;
export default interactionsSlice.reducer;