import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/client";
import { setDraft } from "./interactionsSlice";

export const sendChatMessage = createAsyncThunk(
  "chat/sendMessage",
  async ({ message, hcpId }, { dispatch }) => {
    const res = await api.post("/api/chat", { message, hcp_id: hcpId || null });

    // If the agent extracted a log_interaction draft, bind it into the structured form
    // instead of treating this chat turn as an already-completed database write.
    if (res.data.action === "draft_interaction" && res.data.draft) {
      dispatch(setDraft(res.data.draft));
    }

    return { userMessage: message, ...res.data };
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