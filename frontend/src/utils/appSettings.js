const STORAGE_KEY = "safeguard360-app-settings";
export const APP_SETTINGS_UPDATED_EVENT = "safeguard360:app-settings-updated";

export const DEFAULT_APP_SETTINGS = {
  language: "en-US",
  fleetCamera: "webcam:0",
  attendanceCamera: "webcam-0",
  accessLevel: "regional-supervisor",
};

function normalizeAppSettings(settings = {}) {
  return {
    language: settings.language ?? DEFAULT_APP_SETTINGS.language,
    fleetCamera: settings.fleetCamera ?? DEFAULT_APP_SETTINGS.fleetCamera,
    attendanceCamera:
      settings.attendanceCamera ?? DEFAULT_APP_SETTINGS.attendanceCamera,
    accessLevel: settings.accessLevel ?? DEFAULT_APP_SETTINGS.accessLevel,
  };
}

export function readAppSettings() {
  if (typeof window === "undefined") {
    return { ...DEFAULT_APP_SETTINGS };
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_APP_SETTINGS };
    }

    return normalizeAppSettings(JSON.parse(raw));
  } catch (error) {
    console.error("[appSettings] Failed to read storage", error);
    return { ...DEFAULT_APP_SETTINGS };
  }
}

export function writeAppSettings(settings) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const normalizedSettings = normalizeAppSettings(settings);
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(normalizedSettings),
    );
    window.dispatchEvent(new Event(APP_SETTINGS_UPDATED_EVENT));
  } catch (error) {
    console.error("[appSettings] Failed to write storage", error);
  }
}

export function resetAppSettings() {
  if (typeof window === "undefined") {
    return { ...DEFAULT_APP_SETTINGS };
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
    window.dispatchEvent(new Event(APP_SETTINGS_UPDATED_EVENT));
  } catch (error) {
    console.error("[appSettings] Failed to reset storage", error);
  }

  return { ...DEFAULT_APP_SETTINGS };
}
