import React from "react";
import ReactDOM from "react-dom/client";
import LatencyAnalyzer from "./LatencyAnalyzer";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <LatencyAnalyzer />
  </React.StrictMode>
);
