import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { store } from "./app/store";
import { ReviewQueue } from "./pages/ReviewQueue";
import { RunDetail } from "./pages/RunDetail";
import { RunList } from "./pages/RunList";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Provider store={store}>
      <BrowserRouter>
        <nav className="nav">
          <Link to="/runs">Runs</Link>
          <Link to="/review">Review queue</Link>
        </nav>
        <Routes>
          <Route path="/" element={<Navigate to="/runs" />} />
          <Route path="/runs" element={<RunList />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/review" element={<ReviewQueue />} />
        </Routes>
      </BrowserRouter>
    </Provider>
  </StrictMode>,
);