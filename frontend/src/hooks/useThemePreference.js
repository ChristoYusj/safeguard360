import { useEffect, useState } from "react";

const STORAGE_KEY = "safeguard360-theme";
const THEME_EVENT = "safeguard360-theme-change";

function getInitialTheme() {
  if (typeof window === "undefined") {
    return true;
  }

  const savedTheme = window.localStorage.getItem(STORAGE_KEY);
  if (savedTheme === "light") {
    return false;
  }
  if (savedTheme === "dark") {
    return true;
  }
  return true;
}

export function useThemePreference() {
  const [darkMode, setDarkMode] = useState(getInitialTheme);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, darkMode ? "dark" : "light");
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
    document.body.dataset.theme = darkMode ? "dark" : "light";
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: darkMode ? "dark" : "light" }));
  }, [darkMode]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const syncTheme = (nextTheme) => {
      setDarkMode(nextTheme === "dark");
    };

    const onStorage = (event) => {
      if (event.key === STORAGE_KEY && event.newValue) {
        syncTheme(event.newValue);
      }
    };

    const onThemeEvent = (event) => {
      if (event.detail) {
        syncTheme(event.detail);
      }
    };

    window.addEventListener("storage", onStorage);
    window.addEventListener(THEME_EVENT, onThemeEvent);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(THEME_EVENT, onThemeEvent);
    };
  }, []);

  return {
    darkMode,
    toggleDarkMode: () => setDarkMode((current) => !current),
  };
}
