import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../../api/client";

export const fetchHcps = createAsyncThunk("hcps/fetchAll", async () => {
  const res = await api.get("/api/hcps");
  return res.data;
});

export const createHcp = createAsyncThunk("hcps/create", async (payload) => {
  const res = await api.post("/api/hcps", payload);
  return res.data;
});

const hcpsSlice = createSlice({
  name: "hcps",
  initialState: {
    items: [],
    status: "idle", // idle | loading | succeeded | failed
    error: null,
    selectedHcpId: null,
  },
  reducers: {
    selectHcp(state, action) {
      state.selectedHcpId = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchHcps.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchHcps.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchHcps.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message;
      })
      .addCase(createHcp.fulfilled, (state, action) => {
        state.items.push(action.payload);
        state.selectedHcpId = action.payload.id;
      });
  },
});

export const { selectHcp } = hcpsSlice.actions;
export default hcpsSlice.reducer;
