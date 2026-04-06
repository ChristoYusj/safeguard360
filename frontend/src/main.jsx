import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppLanguageProvider } from "./contexts/AppLanguageContext";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <AppLanguageProvider>
    <App />
  </AppLanguageProvider>,
);
