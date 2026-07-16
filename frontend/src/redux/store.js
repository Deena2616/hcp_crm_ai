// redux/store.js
import { configureStore } from "@reduxjs/toolkit";
import hcpsReducer from "./slices/hcpsSlice";
import interactionsReducer from "./slices/interactionsSlice";
import chatReducer from "./slices/chatSlice";
import followUpsReducer from "./slices/followUpsSlice";

export const store = configureStore({
  reducer: {
    hcps: hcpsReducer,
    interactions: interactionsReducer,
    chat: chatReducer,
    followUps: followUpsReducer,
  },
});