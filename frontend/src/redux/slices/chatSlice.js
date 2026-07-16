import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/client";
import { setDraft, applyEditResult } from "./interactionsSlice";
import { addFollowUp } from "./followUpsSlice";

// Main assistant panel - handles everything: new-interaction drafting, edits, follow-ups,
// searches, and profile lookups, routed by the backend's intent classifier.
export const sendChatMessage = createAsyncThunk(
  "chat/sendMessage",
  async ({ message, hcpId, context }, { dispatch }) => {
    const res = await api.post("/api/chat", { message, hcp_id: hcpId || null, context: context || null });

    // If the agent extracted a log_interaction draft, bind it into the structured form
    // instead of treating this chat turn as an already-completed database write.
    if (res.data.action === "draft_interaction" && res.data.draft) {
      dispatch(setDraft(res.data.draft));
    }

    // edit_interaction_tool commits immediately server-side; sync the local list so the
    // UI reflects it without waiting on a full refetch.
    if (res.data.tool_calls?.includes("edit_interaction_tool") && res.data.data?.status === "updated") {
      dispatch(applyEditResult(res.data.data));
    }

    // schedule_followup_tool also commits immediately; push it into the follow-ups list.
    if (res.data.tool_calls?.includes("schedule_followup_tool") && res.data.data?.status === "scheduled") {
      dispatch(addFollowUp(res.data.data));
    }

    return { userMessage: message, ...res.data };
  }
);

// Dedicated "Edit this entry" prompt area - pins interaction_id via context so a short
// instruction is unambiguous. Still commits immediately, same tool under the hood.
export const sendEditMessage = createAsyncThunk(
  "chat/sendEditMessage",
  async ({ message, interactionId, hcpName }, { dispatch }) => {
    const res = await api.post("/api/chat/edit", {
      message,
      hcp_id: null,
      context: { interaction_id: interactionId, hcp_name: hcpName || null },
    });

    if (res.data.data?.status === "updated") {
      dispatch(applyEditResult(res.data.data));
    }

    return res.data;
  }
);

// Dedicated "Schedule follow-up" prompt area - pins hcp_name via context.
export const sendFollowUpMessage = createAsyncThunk(
  "chat/sendFollowUpMessage",
  async ({ message, hcpName }, { dispatch }) => {
    const res = await api.post("/api/chat/followup", {
      message,
      hcp_id: null,
      context: { hcp_name: hcpName || null },
    });

    if (res.data.data?.status === "scheduled") {
      dispatch(addFollowUp(res.data.data));
    }

    return res.data;
  }
);

const chatSlice = createSlice({
  name: "chat",
  initialState: {
    messages: [],
    status: "idle",
    error: null,
  },
  reducers: {
    clearChat(state) {
      state.messages = [];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendChatMessage.pending, (state, action) => {
        state.status = "loading";
        state.messages.push({ role: "user", text: action.meta.arg.message });
      })
      .addCase(sendChatMessage.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.messages.push({
          role: "assistant",
          text: action.payload.reply,
          intent: action.payload.intent,
          toolCalls: action.payload.tool_calls,
          data: action.payload.data,
        });
      })
      .addCase(sendChatMessage.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message;
        state.messages.push({
          role: "assistant",
          text: "Something went wrong reaching the agent. Please try again.",
          isError: true,
        });
      });
  },
});

export const { clearChat } = chatSlice.actions;
export default chatSlice.reducer;