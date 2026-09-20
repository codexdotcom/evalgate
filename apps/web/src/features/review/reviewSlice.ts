import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

export interface ReviewState {
  cursor: number;
  labeled: Record<string, boolean>;
  sessionStart: number | null;
  sessionCount: number;
  reviewer: string;
  blindMode: boolean;
}

const initialState: ReviewState = {
  cursor: 0,
  labeled: {},
  sessionStart: null,
  sessionCount: 0,
  reviewer: localStorage.getItem("reviewer") ?? "anonymous",
  blindMode: localStorage.getItem("blindMode") === "true",
};

const slice = createSlice({
  name: "review",
  initialState,
  reducers: {
    label(s, a: PayloadAction<{ id: string; passed: boolean }>) {
      s.sessionStart ??= Date.now();
      s.labeled[a.payload.id] = a.payload.passed;
      s.sessionCount += 1;
      s.cursor += 1;
    },
    back(s) {
      s.cursor = Math.max(0, s.cursor - 1);
    },
    reset(s) {
      s.cursor = 0;
      s.labeled = {};
      s.sessionCount = 0;
      s.sessionStart = null;
    },
    setReviewer(s, a: PayloadAction<string>) {
      s.reviewer = a.payload;
      localStorage.setItem("reviewer", a.payload);
    },
    toggleBlind(s) {
      s.blindMode = !s.blindMode;
      localStorage.setItem("blindMode", String(s.blindMode));
    },
  },
});

export const { label, back, reset, setReviewer, toggleBlind } = slice.actions;
export default slice.reducer;

// Date.now() inside a selector means the rate only refreshes when the store
// changes, which is on every label. That is exactly when it should refresh.
export const selectRate = (s: { review: ReviewState }) => {
  const { sessionStart, sessionCount } = s.review;
  if (!sessionStart || sessionCount < 2) return 0;
  return sessionCount / ((Date.now() - sessionStart) / 60000);
};