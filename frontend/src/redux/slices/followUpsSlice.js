import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/client";

export const fetchFollowUps = createAsyncThunk(
  "followUps/fetchAll",
  async (hcpId) => {
    const res = await api.get("/api/followups", { params: hcpId ? { hcp_id: hcpId } : {} });
    return res.data;
  }
);

const followUpsSlice = createSlice({
  name: "followUps",
  initialState: {
    items: [],
    status: "idle",
    error: null,
  },
  reducers: {
    // Applied when schedule_followup_tool commits via chat / the dedicated follow-up
    // prompt area, so the list reflects it immediately.
    addFollowUp(state, action) {
      state.items.unshift(action.payload);
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchFollowUps.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchFollowUps.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchFollowUps.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message;
      });
  },
});

export const { addFollowUp } = followUpsSlice.actions;
export default followUpsSlice.reducer;