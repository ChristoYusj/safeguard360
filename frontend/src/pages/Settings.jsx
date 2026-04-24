import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import PasswordStrength from "../components/auth/PasswordStrength";
import {
  canAccessAttendance,
  canAccessDrivers,
  getRoleLabel,
} from "../utils/accessControl";
import {
  bulkImportPersons,
  changeOperatorPassword,
  deletePerson,
  getPersons,
  updatePerson,
} from "../services/api";
import { useThemePreference } from "../hooks/useThemePreference";
import { useAppLanguage } from "../contexts/AppLanguageContext";
import {
  AttendanceIcon,
  CheckCircleIcon,
  DriversIcon,
  ExternalLinkIcon,
  SettingsIcon,
  UsersIcon,
} from "../components/icons";
import { readAppSettings, writeAppSettings } from "../utils/appSettings";
import { isStrongPassword } from "../utils/passwordValidation";
import {
  DEFAULT_DRIVER_PORTRAIT,
  readTestDatabase,
  writeTestDatabase,
} from "../utils/demoDatabase";

const languageOptions = [
  { value: "en-US", label: "English (US)" },
  { value: "en-GB", label: "English (UK)" },
  { value: "ar-LB", label: "Arabic (Lebanon)" },
];

const attendanceCameraOptions = [
  { value: "webcam-0", label: "Webcam 0" },
  { value: "webcam-1", label: "Webcam 1" },
  { value: "ip-stream", label: "IP stream" },
];

const fleetCameraOptions = [
  { value: "webcam:0", label: "Webcam 0" },
  { value: "webcam:1", label: "Webcam 1" },
  { value: "ip_stream:", label: "IP stream" },
];

const destinationLabels = {
  beirut: "Beirut",
  tripoli: "Tripoli",
  achrafieh: "Achrafieh",
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

const supportEmail = import.meta.env.VITE_SUPPORT_EMAIL?.trim() || "";
const ENROLLMENT_SHIFT_LABELS = {
  day: "Day Shift",
  swing: "Swing Shift",
  night: "Night Shift",
};
const SECURITY_PANELS = {
  PASSWORD: "password",
  TWO_FACTOR: "twoFactor",
};

function normalizeWorkerMatchValue(value) {
  return value?.trim().toLowerCase() || "";
}

function mapWorkerShiftToEnrollmentShift(shiftLabel) {
  const value = shiftLabel?.trim().toLowerCase() || "";

  if (!value) {
    return "day";
  }

  if (value.includes("night")) {
    return "night";
  }

  if (value.includes("mid") || value.includes("swing") || value.includes("late")) {
    return "swing";
  }

  return "day";
}

function getMatchedEnrollmentPerson(worker, persons) {
  const normalizedBadgeId = normalizeWorkerMatchValue(worker.badgeId);
  const normalizedName = normalizeWorkerMatchValue(worker.name);
  const linkedPersonId = worker.enrollmentPersonId;

  return (
    persons.find((person) => {
      if (linkedPersonId && String(person.id) === String(linkedPersonId)) {
        return true;
      }

      const normalizedEmployeeId = normalizeWorkerMatchValue(person.employee_id);
      const normalizedPersonName = normalizeWorkerMatchValue(person.name);

      return (
        (normalizedBadgeId && normalizedEmployeeId === normalizedBadgeId) ||
        (normalizedName && normalizedPersonName === normalizedName)
      );
    }) || null
  );
}

function mapEnrollmentPersonToWorker(person) {
  return {
    id: `worker-person-${person.id}`,
    enrollmentPersonId: person.id,
    syncSource: "enrollment",
    name: person.name || "Unnamed worker",
    badgeId: person.employee_id || "",
    shift: ENROLLMENT_SHIFT_LABELS[person.shift_id] || "Day Shift",
    portrait: person.thumbnail_data_url || DEFAULT_DRIVER_PORTRAIT,
    addedAt: person.created_at || new Date().toISOString(),
    isActive: person.is_active !== false,
    hasEmbedding: Boolean(person.has_embedding),
    embeddingCount: Number(person.embedding_count ?? 0),
    sampleCount: Number(person.sample_count ?? 0),
  };
}

function mergeAttendanceWorkersWithPersons(attendanceWorkers, persons) {
  const matchedPersonIds = new Set();

  const mergedWorkers = attendanceWorkers
    .map((worker) => {
      const matchedPerson = getMatchedEnrollmentPerson(worker, persons);

      if (worker.syncSource === "enrollment" && !matchedPerson) {
        return null;
      }

      if (!matchedPerson) {
        const { enrollmentPersonId, syncSource, ...localWorker } = worker;
        return { ...localWorker, isActive: worker.isActive !== false };
      }

      matchedPersonIds.add(String(matchedPerson.id));

      return {
        ...worker,
        enrollmentPersonId: matchedPerson.id,
        name: matchedPerson.name || worker.name,
        badgeId: matchedPerson.employee_id || worker.badgeId,
        shift:
          ENROLLMENT_SHIFT_LABELS[matchedPerson.shift_id] ||
          worker.shift ||
          "Day Shift",
        portrait: matchedPerson.thumbnail_data_url || worker.portrait,
        addedAt: worker.addedAt || matchedPerson.created_at || new Date().toISOString(),
        isActive: matchedPerson.is_active !== false,
        hasEmbedding: Boolean(matchedPerson.has_embedding),
        embeddingCount: Number(matchedPerson.embedding_count ?? 0),
        sampleCount: Number(matchedPerson.sample_count ?? 0),
      };
    })
    .filter(Boolean);

  const syncedEnrollmentOnlyWorkers = persons
    .filter((person) => !matchedPersonIds.has(String(person.id)))
    .map((person) => mapEnrollmentPersonToWorker(person));

  return [...mergedWorkers, ...syncedEnrollmentOnlyWorkers];
}

function ToggleSwitch({ checked, onChange, ariaLabel }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={onChange}
      className={`relative h-7 w-12 rounded-full transition-colors ${
        checked
          ? "bg-[var(--color-accent-primary)]"
          : "bg-[var(--color-border-emphasis)]"
      }`}
    >
      <span
        className={`absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow-md transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function SettingRow({ label, description, control }) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-default bg-surface px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="min-w-0">
        <p className="font-semibold text-primary">{label}</p>
        <p className="mt-1 text-sm text-secondary">{description}</p>
      </div>
      <div className="w-full lg:w-[250px]">{control}</div>
    </div>
  );
}

function formatTimestamp(value) {
  if (!value) {
    return "Added just now";
  }

  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function createDatabaseId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createDriverFormTemplate(database) {
  return {
    name: "",
    stateId: "",
    role:
      database.driverOptionHistory?.roles?.[0] || database.drivers[0]?.role || "",
    assignedRoute:
      database.driverOptionHistory?.assignedRoutes?.[0] ||
      database.drivers[0]?.assignedRoute ||
      "",
    shift:
      database.driverOptionHistory?.shifts?.[0] ||
      database.drivers[0]?.shift ||
      "",
    destinationKey:
      database.driverOptionHistory?.destinationKeys?.[0] ||
      database.drivers[0]?.destinationKey ||
      "beirut",
    portrait: DEFAULT_DRIVER_PORTRAIT,
  };
}

function createWorkerFormTemplate(drivers, worker) {
  return {
    name: worker?.name || "",
    badgeId: worker?.badgeId || "",
    shift: worker?.shift || drivers[0]?.shift || "",
    portrait: worker?.portrait || DEFAULT_DRIVER_PORTRAIT,
  };
}

function buildTruckIdFromStateId(stateId) {
  const compact = stateId.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
  const suffix = compact.slice(-4).padStart(4, "0");
  return `TRK-${suffix}`;
}

function Settings() {
  const navigate = useNavigate();
  const {
    user,
    refreshUser,
    startTwoFactorSetup,
    confirmTwoFactorEnable,
    disableTwoFactorAuth,
  } = useAuth();
  const { darkMode, toggleDarkMode } = useThemePreference();
  const { t } = useAppLanguage();
  const [settings, setSettings] = useState(readAppSettings);
  const [database, setDatabase] = useState(readTestDatabase);
  const [driverForm, setDriverForm] = useState(() =>
    createDriverFormTemplate(readTestDatabase()),
  );
  const [workerForm, setWorkerForm] = useState(() =>
    createWorkerFormTemplate(readTestDatabase().drivers),
  );
  const [showDriverForm, setShowDriverForm] = useState(false);
  const [showWorkerForm, setShowWorkerForm] = useState(false);
  const [editingDriverId, setEditingDriverId] = useState(null);
  const [editingWorkerId, setEditingWorkerId] = useState(null);
  const [workerSuccessPrompt, setWorkerSuccessPrompt] = useState(null);
  const [workerError, setWorkerError] = useState("");
  const [enrollmentPersons, setEnrollmentPersons] = useState([]);
  const [showInactiveWorkers, setShowInactiveWorkers] = useState(true);
  const [isImportingRoster, setIsImportingRoster] = useState(false);
  const [rosterImportSummary, setRosterImportSummary] = useState(null);
  const [rosterImportError, setRosterImportError] = useState("");
  const csvInputRef = useRef(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState(null);
  const [twoFactorEnableCode, setTwoFactorEnableCode] = useState("");
  const [twoFactorDisableForm, setTwoFactorDisableForm] = useState({
    current_password: "",
    code: "",
  });
  const [twoFactorBackupCodes, setTwoFactorBackupCodes] = useState([]);
  const [twoFactorMessage, setTwoFactorMessage] = useState("");
  const [twoFactorError, setTwoFactorError] = useState("");
  const [twoFactorBusy, setTwoFactorBusy] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    password: "",
    confirm_password: "",
  });
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [activeSecurityPanel, setActiveSecurityPanel] = useState(SECURITY_PANELS.PASSWORD);
  const isAdmin = user?.role === "admin";
  const canViewFleetSettings = canAccessDrivers(user?.role);
  const canViewAttendanceSettings = canAccessAttendance(user?.role);

  useEffect(() => {
    writeAppSettings(settings);
  }, [settings]);

  useEffect(() => {
    writeTestDatabase(database);
  }, [database]);

  const syncEnrolledWorkers = async () => {
    const persons = await getPersons({ includeInactive: true });
    setEnrollmentPersons(persons || []);
    setDatabase((current) => ({
      ...current,
      attendanceWorkers: mergeAttendanceWorkersWithPersons(
        current.attendanceWorkers,
        persons || [],
      ),
    }));
    return persons || [];
  };

  const handleCsvImport = async (event) => {
    const file = event.target.files?.[0];
    if (csvInputRef.current) {
      csvInputRef.current.value = "";
    }
    if (!file) return;

    setIsImportingRoster(true);
    setRosterImportError("");
    setRosterImportSummary(null);
    try {
      const summary = await bulkImportPersons(file);
      setRosterImportSummary(summary);
      await syncEnrolledWorkers();
    } catch (importError) {
      setRosterImportError(importError.message || "Roster import failed.");
    } finally {
      setIsImportingRoster(false);
    }
  };

  const handleToggleWorkerActive = async (worker) => {
    if (!worker) return;
    const matchedPerson = getMatchedEnrollmentPerson(worker, enrollmentPersons);
    if (!matchedPerson) {
      setWorkerError(
        "Active status is only tracked for enrolled workers. Enroll this worker first.",
      );
      return;
    }

    const nextActive = !(worker.isActive !== false);
    setWorkerError("");
    try {
      // PersonUpsertRequest requires name (min 1 char); shift_id must match
      // the ^(day|swing|night)$ pattern or be null. Reuse the record that
      // came back from the backend so we don't strip existing fields.
      const validShift = ["day", "swing", "night"].includes(
        matchedPerson.shift_id,
      )
        ? matchedPerson.shift_id
        : null;

      await updatePerson(matchedPerson.id, {
        name: matchedPerson.name,
        employee_id: matchedPerson.employee_id || null,
        shift_id: validShift,
        is_active: nextActive,
      });
      setEnrollmentPersons((current) =>
        current.map((person) =>
          String(person.id) === String(matchedPerson.id)
            ? { ...person, is_active: nextActive }
            : person,
        ),
      );
      setDatabase((current) => ({
        ...current,
        attendanceWorkers: current.attendanceWorkers.map((entry) =>
          entry.id === worker.id ? { ...entry, isActive: nextActive } : entry,
        ),
      }));
    } catch (toggleError) {
      // FastAPI validation errors come back as an array under `detail`; the
      // default `new Error(array)` stringifies to "[object Object]". Build
      // a readable message from whichever shape we got.
      const readable =
        (typeof toggleError.message === "string" &&
          toggleError.message !== "[object Object]" &&
          toggleError.message) ||
        (Array.isArray(toggleError.detail) &&
          toggleError.detail
            .map((d) => d?.msg || JSON.stringify(d))
            .join("; ")) ||
        "Failed to update worker active status.";
      setWorkerError(readable);
    }
  };

  useEffect(() => {
    let isMounted = true;

    if (isAdmin) {
      syncEnrolledWorkers().catch((error) => {
        if (isMounted) {
          console.error("Failed to sync enrolled workers into Settings.", error);
        }
      });
    }

    return () => {
      isMounted = false;
    };
  }, [canViewAttendanceSettings, isAdmin]);

  const signedInEmail = user?.email || "No operator signed in";
  const accountType = getRoleLabel(user?.role);
  const passwordIsStrong = useMemo(
    () => isStrongPassword(passwordForm.password),
    [passwordForm.password],
  );
  const passwordsMatch =
    passwordForm.password.length > 0 &&
    passwordForm.password === passwordForm.confirm_password;
  const driverRoleOptions = useMemo(
    () => database.driverOptionHistory?.roles || [],
    [database.driverOptionHistory],
  );
  const driverRouteOptions = useMemo(
    () => database.driverOptionHistory?.assignedRoutes || [],
    [database.driverOptionHistory],
  );
  const driverShiftOptions = useMemo(
    () => database.driverOptionHistory?.shifts || [],
    [database.driverOptionHistory],
  );
  const driverDestinationOptions = useMemo(
    () => database.driverOptionHistory?.destinationKeys || [],
    [database.driverOptionHistory],
  );

  const variantColors = {
    success: "var(--color-success)",
    warning: "var(--color-warning)",
    info: "var(--color-info)",
  };

  const coreServices = useMemo(
    () => [
      {
        label: "Fleet Driver Database",
        status:
          database.drivers.length > 0
            ? `${database.drivers.length} stored`
            : "Awaiting drivers",
        variant: database.drivers.length > 0 ? "success" : "warning",
      },
      {
        label: "Attendance Worker Database",
        status:
          database.attendanceWorkers.length > 0
            ? `${database.attendanceWorkers.length} stored`
            : "Awaiting workers",
        variant: database.attendanceWorkers.length > 0 ? "success" : "warning",
      },
    ],
    [database.attendanceWorkers.length, database.drivers.length],
  );

  const updateSetting = (key, value) => {
    setSettings((current) => ({
      ...current,
      [key]: value,
    }));
  };

  const handleStartTwoFactorSetup = async () => {
    setActiveSecurityPanel(SECURITY_PANELS.TWO_FACTOR);
    setTwoFactorBusy(true);
    setTwoFactorError("");
    setTwoFactorMessage("");
    setTwoFactorBackupCodes([]);
    try {
      const setup = await startTwoFactorSetup();
      setTwoFactorSetup(setup);
      setTwoFactorEnableCode("");
    } catch (error) {
      setTwoFactorError(error.message || "Two-factor setup could not be started.");
    } finally {
      setTwoFactorBusy(false);
    }
  };

  const handleConfirmTwoFactorEnable = async (event) => {
    event.preventDefault();
    setActiveSecurityPanel(SECURITY_PANELS.TWO_FACTOR);
    setTwoFactorBusy(true);
    setTwoFactorError("");
    setTwoFactorMessage("");
    try {
      const response = await confirmTwoFactorEnable({ code: twoFactorEnableCode });
      setTwoFactorBackupCodes(response.backup_codes || []);
      setTwoFactorSetup(null);
      setTwoFactorEnableCode("");
      setTwoFactorMessage(response.message || "Two-factor authentication is enabled.");
    } catch (error) {
      setTwoFactorError(error.message || "Two-factor confirmation failed.");
    } finally {
      setTwoFactorBusy(false);
    }
  };

  const handleDisableTwoFactor = async (event) => {
    event.preventDefault();
    setActiveSecurityPanel(SECURITY_PANELS.TWO_FACTOR);
    setTwoFactorBusy(true);
    setTwoFactorError("");
    setTwoFactorMessage("");
    try {
      const response = await disableTwoFactorAuth(twoFactorDisableForm);
      setTwoFactorDisableForm({
        current_password: "",
        code: "",
      });
      setTwoFactorBackupCodes([]);
      setTwoFactorMessage(response.message || "Two-factor authentication was disabled.");
    } catch (error) {
      setTwoFactorError(error.message || "Two-factor disable failed.");
    } finally {
      setTwoFactorBusy(false);
    }
  };

  const handleAddDriver = (event) => {
    event.preventDefault();

    if (!driverForm.name.trim() || !driverForm.stateId.trim()) {
      return;
    }

    const fallbackProfile = database.drivers.find(
      (driver) =>
        driver.role === driverForm.role ||
        driver.assignedRoute === driverForm.assignedRoute ||
        driver.shift === driverForm.shift,
    );
    const truckId = buildTruckIdFromStateId(driverForm.stateId.trim());
    const currentDriver = database.drivers.find(
      (driver) => driver.id === editingDriverId,
    );
    const nextDriver = {
      id: editingDriverId || createDatabaseId("driver"),
      name: driverForm.name.trim(),
      fullName: driverForm.name.trim(),
      vehicle: truckId,
      truckId,
      stateId: driverForm.stateId.trim(),
      role: driverForm.role,
      licenseClass:
        currentDriver?.licenseClass ||
        fallbackProfile?.licenseClass ||
        database.drivers[0]?.licenseClass ||
        "C1E",
      assignedRoute: driverForm.assignedRoute,
      shift: driverForm.shift,
      destinationKey: driverForm.destinationKey,
      portrait: driverForm.portrait || DEFAULT_DRIVER_PORTRAIT,
      addedAt: currentDriver?.addedAt || new Date().toISOString(),
    };

    setDatabase((current) => ({
      ...current,
      drivers: editingDriverId
        ? current.drivers.map((driver) =>
            driver.id === editingDriverId ? nextDriver : driver,
          )
        : [nextDriver, ...current.drivers],
      driverOptionHistory: {
        roles: [...new Set([driverForm.role, ...(current.driverOptionHistory?.roles || [])])].filter(Boolean),
        assignedRoutes: [
          ...new Set([
            driverForm.assignedRoute,
            ...(current.driverOptionHistory?.assignedRoutes || []),
          ]),
        ].filter(Boolean),
        shifts: [...new Set([driverForm.shift, ...(current.driverOptionHistory?.shifts || [])])].filter(Boolean),
        destinationKeys: [
          ...new Set([
            driverForm.destinationKey,
            ...(current.driverOptionHistory?.destinationKeys || []),
          ]),
        ].filter(Boolean),
      },
    }));
    setDriverForm(createDriverFormTemplate(database));
    setShowDriverForm(false);
    setEditingDriverId(null);
  };

  const handleDriverPortraitUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== "image/png") {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      setDriverForm((current) => ({
        ...current,
        portrait:
          typeof reader.result === "string"
            ? reader.result
            : DEFAULT_DRIVER_PORTRAIT,
      }));
    };
    reader.readAsDataURL(file);
  };

  const handleEditDriver = (driver) => {
    setEditingDriverId(driver.id);
    setDriverForm({
      name: driver.name || driver.fullName || "",
      stateId: driver.stateId || "",
      role: driver.role || driverRoleOptions[0] || "",
      assignedRoute: driver.assignedRoute || driverRouteOptions[0] || "",
      shift: driver.shift || driverShiftOptions[0] || "",
      destinationKey: driver.destinationKey || driverDestinationOptions[0] || "beirut",
      portrait: driver.portrait || DEFAULT_DRIVER_PORTRAIT,
    });
    setShowDriverForm(true);
  };

  const resetDriverEditor = () => {
    setDriverForm(createDriverFormTemplate(database));
    setShowDriverForm(false);
    setEditingDriverId(null);
  };

  const handleDeleteDriver = (driverId) => {
    setDatabase((current) => ({
      ...current,
      drivers: current.drivers.filter((driver) => driver.id !== driverId),
    }));

    if (editingDriverId === driverId) {
      resetDriverEditor();
    }
  };

  const handleAddWorker = async (event) => {
    event.preventDefault();

    if (!workerForm.name.trim() || !workerForm.badgeId.trim()) {
      return;
    }

    const isNewWorker = !editingWorkerId;
    const currentWorker = database.attendanceWorkers.find(
      (worker) => worker.id === editingWorkerId,
    );
    const matchedEnrollmentPerson = getMatchedEnrollmentPerson(
      currentWorker || workerForm,
      enrollmentPersons,
    );
    const nextWorker = {
      id: editingWorkerId || createDatabaseId("worker"),
      enrollmentPersonId:
        currentWorker?.enrollmentPersonId || matchedEnrollmentPerson?.id || null,
      syncSource:
        currentWorker?.syncSource ||
        (matchedEnrollmentPerson ? "enrollment" : undefined),
      name: workerForm.name.trim(),
      badgeId: workerForm.badgeId.trim(),
      shift: workerForm.shift,
      portrait: workerForm.portrait || DEFAULT_DRIVER_PORTRAIT,
      addedAt: currentWorker?.addedAt || new Date().toISOString(),
    };

    setWorkerError("");

    try {
      if (matchedEnrollmentPerson) {
        await updatePerson(matchedEnrollmentPerson.id, {
          name: nextWorker.name,
          employee_id: nextWorker.badgeId || null,
          shift_id: mapWorkerShiftToEnrollmentShift(nextWorker.shift),
          is_active: true,
        });
        setEnrollmentPersons((current) =>
          current.map((person) =>
            String(person.id) === String(matchedEnrollmentPerson.id)
              ? {
                  ...person,
                  name: nextWorker.name,
                  employee_id: nextWorker.badgeId || null,
                  shift_id: mapWorkerShiftToEnrollmentShift(nextWorker.shift),
                }
              : person,
          ),
        );
      }

      setDatabase((current) => ({
        ...current,
        attendanceWorkers: editingWorkerId
          ? current.attendanceWorkers.map((worker) =>
              worker.id === editingWorkerId ? nextWorker : worker,
            )
          : [nextWorker, ...current.attendanceWorkers],
      }));
      setWorkerSuccessPrompt(
        isNewWorker
          ? {
              workerId: nextWorker.id,
              workerName: nextWorker.name,
            }
          : null,
      );
      setWorkerForm(
        createWorkerFormTemplate(database.drivers),
      );
      setShowWorkerForm(false);
      setEditingWorkerId(null);
    } catch (error) {
      setWorkerError(error.message || "Failed to save worker.");
    }
  };

  const handleWorkerPortraitUpload = (event) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== "image/png") {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      setWorkerForm((current) => ({
        ...current,
        portrait:
          typeof reader.result === "string"
            ? reader.result
            : DEFAULT_DRIVER_PORTRAIT,
      }));
    };
    reader.readAsDataURL(file);
  };

  const handleEditWorker = (worker) => {
    setWorkerError("");
    setWorkerSuccessPrompt(null);
    setEditingWorkerId(worker.id);
    setWorkerForm(
      createWorkerFormTemplate(database.drivers, worker),
    );
    setShowWorkerForm(true);
  };

  const resetWorkerEditor = () => {
    setWorkerError("");
    setWorkerForm(
      createWorkerFormTemplate(database.drivers),
    );
    setShowWorkerForm(false);
    setEditingWorkerId(null);
  };

  const handleDeleteWorker = async (workerId) => {
    const worker = database.attendanceWorkers.find((entry) => entry.id === workerId);
    const matchedEnrollmentPerson = worker
      ? getMatchedEnrollmentPerson(worker, enrollmentPersons)
      : null;

    setWorkerError("");

    try {
      if (matchedEnrollmentPerson) {
        await deletePerson(matchedEnrollmentPerson.id);
        setEnrollmentPersons((current) =>
          current.filter(
            (person) => String(person.id) !== String(matchedEnrollmentPerson.id),
          ),
        );
      }

      setDatabase((current) => ({
        ...current,
        attendanceWorkers: current.attendanceWorkers.filter(
          (worker) => worker.id !== workerId,
        ),
      }));

      if (editingWorkerId === workerId) {
        resetWorkerEditor();
      }
    } catch (error) {
      setWorkerError(error.message || "Failed to delete worker.");
    }
  };

  const handleChangePassword = async (event) => {
    event.preventDefault();
    setActiveSecurityPanel(SECURITY_PANELS.PASSWORD);
    if (passwordBusy) {
      return;
    }

    if (!passwordForm.current_password.trim()) {
      setPasswordError("Current password is required.");
      return;
    }

    if (!passwordIsStrong) {
      setPasswordError(
        "Password must be at least 8 characters and include an uppercase letter, number, and special character.",
      );
      return;
    }

    if (!passwordsMatch) {
      setPasswordError("Passwords do not match.");
      return;
    }

    setPasswordBusy(true);
    setPasswordError("");
    setPasswordMessage("");
    try {
      const response = await changeOperatorPassword(passwordForm);
      setPasswordForm({
        current_password: "",
        password: "",
        confirm_password: "",
      });
      setPasswordMessage(response.message || "Password updated successfully.");
      await refreshUser();
    } catch (changeError) {
      setPasswordError(changeError.message || "Password could not be updated.");
    } finally {
      setPasswordBusy(false);
    }
  };

  const supportHref = supportEmail
    ? `mailto:${supportEmail}?subject=${encodeURIComponent(
        "Dashboard support request",
      )}&body=${encodeURIComponent(
        `I need dashboard support for the account ${signedInEmail || "in this browser session"}.`,
      )}`
    : null;

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">
          {isAdmin ? t("platform_configuration") : "Operator Settings"}
        </p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          {isAdmin ? t("settings") : "Account, Security & Access"}
        </h1>
      </motion.section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <motion.section
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="space-y-6"
          >
          <motion.article variants={itemVariants} className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <SettingsIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <h2 className="font-display text-xl font-semibold text-primary">
                  {isAdmin ? t("workspace_controls") : "Personal Preferences"}
                </h2>
              </div>
            </div>
            <div className="panel__content space-y-3">
              <SettingRow
                label={t("theme_preference")}
                description={t("theme_preference_description")}
                control={
                  <div className="flex items-center justify-between rounded-xl border border-default bg-card px-4 py-3">
                    <span className="text-sm font-semibold text-primary">
                      {darkMode
                        ? t("dark_command_center")
                        : t("light_command_center")}
                    </span>
                    <ToggleSwitch
                      checked={darkMode}
                      onChange={toggleDarkMode}
                      ariaLabel="Toggle interface theme"
                    />
                  </div>
                }
              />
              <SettingRow
                label={t("language")}
                description={t("language_description")}
                control={
                  <select
                    value={settings.language}
                    onChange={(event) =>
                      updateSetting("language", event.target.value)
                    }
                    className="input h-12"
                  >
                    {languageOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                }
              />
            </div>
          </motion.article>

          {canViewFleetSettings ? (
          <motion.article variants={itemVariants} className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <DriversIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <h2 className="font-display text-xl font-semibold text-primary">
                    {t("fleet_monitoring")}
                  </h2>
                  <p className="mt-1 text-sm text-secondary">
                    {isAdmin
                      ? `${database.drivers.length} driver${database.drivers.length === 1 ? "" : "s"} stored locally.`
                      : "Fleet camera and monitoring preferences for your role."}
                  </p>
                </div>
              </div>
            </div>
            <div className="panel__content space-y-4">
              <SettingRow
                label={t("camera")}
                description={t("fleet_camera_description")}
                control={
                  <select
                    value={settings.fleetCamera}
                    onChange={(event) =>
                      updateSetting("fleetCamera", event.target.value)
                    }
                    className="input h-12"
                  >
                    {fleetCameraOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                }
              />

              {isAdmin ? (
              <div className="rounded-xl border border-default bg-surface px-5 py-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="font-semibold text-primary">{t("driver_database")}</p>
                    <p className="mt-1 text-sm text-secondary">
                      {t("driver_database_description")}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (showDriverForm && !editingDriverId) {
                        resetDriverEditor();
                        return;
                      }
                      setEditingDriverId(null);
                      setShowDriverForm(true);
                      setDriverForm(createDriverFormTemplate(database));
                    }}
                    className="btn btn-secondary h-11 px-4"
                  >
                    {t("add_driver")}
                  </button>
                </div>

                {showDriverForm ? (
                  <form
                    onSubmit={handleAddDriver}
                    className="mt-4 grid gap-3 rounded-xl border border-default bg-card p-4 md:grid-cols-2"
                  >
                    <input
                      type="text"
                      value={driverForm.name}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      placeholder={t("driver_name_placeholder")}
                      className="input h-12"
                    />
                    <input
                      type="text"
                      value={driverForm.stateId}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          stateId: event.target.value,
                        }))
                      }
                      placeholder={t("driver_id_placeholder")}
                      className="input h-12"
                    />
                    <select
                      value={driverForm.role}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          role: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {driverRoleOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <select
                      value={driverForm.assignedRoute}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          assignedRoute: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {driverRouteOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <select
                      value={driverForm.shift}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          shift: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {driverShiftOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <select
                      value={driverForm.destinationKey}
                      onChange={(event) =>
                        setDriverForm((current) => ({
                          ...current,
                          destinationKey: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {driverDestinationOptions.map((option) => (
                        <option key={option} value={option}>
                          {destinationLabels[option] || option}
                        </option>
                      ))}
                    </select>
                    <div className="rounded-xl border border-default bg-surface p-4 md:col-span-2">
                      <div className="flex flex-col gap-4 md:flex-row md:items-center">
                        <img
                          src={driverForm.portrait || DEFAULT_DRIVER_PORTRAIT}
                          alt="Driver profile preview"
                          className="h-20 w-20 rounded-xl border border-default object-cover"
                        />
                        <div className="flex-1">
                          <label className="block text-sm font-semibold text-primary">
                            {t("profile_picture")}
                          </label>
                          <p className="mt-1 text-sm text-secondary">
                            {t("profile_picture_description")}
                          </p>
                          <input
                            type="file"
                            accept="image/png"
                            onChange={handleDriverPortraitUpload}
                            className="mt-3 block w-full text-sm text-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--color-accent-primary)] file:px-4 file:py-2 file:font-semibold file:text-white"
                          />
                        </div>
                      </div>
                    </div>
                    <button type="submit" className="btn btn-primary h-12 px-4">
                      {editingDriverId ? t("save_changes") : t("save_driver")}
                    </button>
                    <button
                      type="button"
                      onClick={resetDriverEditor}
                      className="btn btn-secondary h-12 px-4"
                    >
                      {t("cancel")}
                    </button>
                  </form>
                ) : null}

                <div className="mt-4 space-y-3">
                  {database.drivers.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-default bg-card px-5 py-6 text-sm text-secondary">
                      {t("no_drivers_yet")}
                    </div>
                  ) : (
                    database.drivers
                      .filter((driver) => driver.id !== editingDriverId)
                      .map((driver) => (
                      <div
                        key={driver.id}
                        className="rounded-2xl border border-default bg-card px-5 py-4"
                      >
                        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                          <div className="flex items-center gap-4">
                            <img
                              src={driver.portrait || DEFAULT_DRIVER_PORTRAIT}
                              alt={driver.name}
                              className="h-16 w-16 rounded-xl border border-default object-cover"
                            />
                            <div>
                              <p className="text-xl font-semibold leading-tight text-primary">
                                {driver.name}
                              </p>
                              <p className="mt-1 text-base leading-snug text-secondary">
                                {[driver.stateId, driver.role, destinationLabels[driver.destinationKey] || driver.destinationKey]
                                  .filter(Boolean)
                                  .join(" • ")}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {driver.shift ? (
                                  <span className="badge badge-info">{driver.shift}</span>
                                ) : null}
                                {driver.assignedRoute ? (
                                  <span className="badge badge-accent">{driver.assignedRoute}</span>
                                ) : null}
                              </div>
                            </div>
                          </div>
                          <div className="ml-4 flex w-[112px] shrink-0 flex-col items-end gap-2">
                            <span className="rounded-full border border-default bg-surface px-3 py-1 text-xs text-secondary whitespace-nowrap">
                              {formatTimestamp(driver.addedAt)}
                            </span>
                            <div className="flex w-full flex-col gap-1.5">
                              <button
                                type="button"
                                onClick={() => handleEditDriver(driver)}
                                className="btn btn-secondary h-8 w-full px-3 text-sm"
                              >
                                {t("edit")}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteDriver(driver.id)}
                                className="btn h-8 w-full px-3 text-sm text-white"
                                style={{
                                  backgroundColor: "var(--color-error)",
                                  borderColor: "transparent",
                                }}
                              >
                                {t("delete")}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
              ) : null}
            </div>
          </motion.article>
          ) : null}

          {canViewAttendanceSettings ? (
          <motion.article variants={itemVariants} className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <AttendanceIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <h2 className="font-display text-xl font-semibold text-primary">
                    {t("attendance_ppe")}
                  </h2>
                  <p className="mt-1 text-sm text-secondary">
                    {isAdmin
                      ? `${database.attendanceWorkers.length} worker${database.attendanceWorkers.length === 1 ? "" : "s"} available in the worker database.`
                      : "Attendance gate and camera controls for this role."}
                  </p>
                </div>
              </div>
            </div>
            <div className="panel__content space-y-4">
              <SettingRow
                label={t("camera")}
                description={t("attendance_camera_description")}
                control={
                  <select
                    value={settings.attendanceCamera}
                    onChange={(event) =>
                      updateSetting("attendanceCamera", event.target.value)
                    }
                    className="input h-12"
                  >
                    {attendanceCameraOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                }
              />

              {isAdmin ? (
              <div className="rounded-xl border border-default bg-surface px-5 py-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="font-semibold text-primary">{t("worker_database")}</p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      ref={csvInputRef}
                      type="file"
                      accept=".csv,text/csv"
                      onChange={handleCsvImport}
                      className="hidden"
                    />
                    <button
                      type="button"
                      onClick={() => csvInputRef.current?.click()}
                      disabled={isImportingRoster}
                      className="btn btn-secondary h-11 px-4"
                      title="Columns: name (required), employee_id, shift_id (day|swing|night), is_active"
                    >
                      {isImportingRoster ? "Importing..." : "Import CSV"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setWorkerSuccessPrompt(null);
                        if (showWorkerForm && !editingWorkerId) {
                          resetWorkerEditor();
                          return;
                        }
                        setEditingWorkerId(null);
                        setShowWorkerForm(true);
                        setWorkerForm(createWorkerFormTemplate(database.drivers));
                      }}
                      className="btn btn-secondary h-11 px-4"
                    >
                      {t("add_worker")}
                    </button>
                  </div>
                </div>

                {rosterImportSummary ? (
                  <div className="mt-4 rounded-xl border border-default bg-card px-4 py-3 text-sm">
                    <p className="font-semibold text-primary">
                      Roster import · {rosterImportSummary.total_rows} row
                      {rosterImportSummary.total_rows === 1 ? "" : "s"} processed
                    </p>
                    <p className="mt-1 text-secondary">
                      {rosterImportSummary.created} created ·{" "}
                      {rosterImportSummary.updated} updated
                      {rosterImportSummary.skipped
                        ? ` · ${rosterImportSummary.skipped} skipped`
                        : ""}
                    </p>
                    {rosterImportSummary.errors?.length ? (
                      <ul className="mt-2 space-y-1 text-xs text-secondary">
                        {rosterImportSummary.errors.slice(0, 5).map((err) => (
                          <li key={`${err.line}-${err.reason}`}>
                            Line {err.line}: {err.reason}
                          </li>
                        ))}
                        {rosterImportSummary.errors.length > 5 ? (
                          <li>+{rosterImportSummary.errors.length - 5} more…</li>
                        ) : null}
                      </ul>
                    ) : null}
                  </div>
                ) : null}

                {rosterImportError ? (
                  <div className="mt-4 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                    <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                      {rosterImportError}
                    </p>
                  </div>
                ) : null}

                <div className="mt-4 flex items-center justify-between rounded-xl border border-default bg-card px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-primary">
                      Show inactive workers
                    </p>
                  </div>
                  <ToggleSwitch
                    checked={showInactiveWorkers}
                    onChange={() => setShowInactiveWorkers((v) => !v)}
                    ariaLabel="Show inactive workers"
                  />
                </div>

                {workerSuccessPrompt ? (
                  <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-4 rounded-2xl border px-5 py-4"
                    style={{
                      borderColor: "color-mix(in srgb, var(--color-success) 65%, transparent)",
                      background:
                        "linear-gradient(135deg, color-mix(in srgb, var(--color-success-muted) 78%, transparent), color-mix(in srgb, var(--color-success) 12%, transparent))",
                    }}
                  >
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div className="flex items-start gap-3">
                        <div
                          className="flex h-11 w-11 items-center justify-center rounded-2xl"
                          style={{
                            backgroundColor:
                              "color-mix(in srgb, var(--color-success) 18%, transparent)",
                            color: "var(--color-success)",
                          }}
                        >
                          <CheckCircleIcon size={22} />
                        </div>
                        <div>
                          <p
                            className="text-sm font-semibold"
                            style={{ color: "var(--color-success)" }}
                          >
                            {workerSuccessPrompt.workerName} saved successfully.
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            Go to Enrollment to add this worker&apos;s face media.
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            navigate(
                              `/enrollment?workerId=${encodeURIComponent(
                                workerSuccessPrompt.workerId,
                              )}`,
                            )
                          }
                          className="btn btn-primary h-10 px-4"
                        >
                          Go to Enrollment
                        </button>
                        <button
                          type="button"
                          onClick={() => setWorkerSuccessPrompt(null)}
                          className="btn btn-secondary h-10 px-4"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  </motion.div>
                ) : null}

                {workerError ? (
                  <div className="mt-4 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                    <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                      {workerError}
                    </p>
                  </div>
                ) : null}

                {showWorkerForm ? (
                  <form
                    onSubmit={handleAddWorker}
                    className="mt-4 grid gap-3 rounded-xl border border-default bg-card p-4 md:grid-cols-2"
                  >
                    <input
                      type="text"
                      value={workerForm.name}
                      onChange={(event) =>
                        setWorkerForm((current) => ({
                          ...current,
                          name: event.target.value,
                        }))
                      }
                      placeholder={t("worker_name_placeholder")}
                      className="input h-12"
                    />
                    <input
                      type="text"
                      value={workerForm.badgeId}
                      onChange={(event) =>
                        setWorkerForm((current) => ({
                          ...current,
                          badgeId: event.target.value,
                        }))
                      }
                      placeholder={t("worker_id_placeholder")}
                      className="input h-12"
                    />
                    <select
                      value={workerForm.shift}
                      onChange={(event) =>
                        setWorkerForm((current) => ({
                          ...current,
                          shift: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {driverShiftOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <div className="rounded-xl border border-default bg-surface p-4 md:col-span-2">
                      <div className="flex flex-col gap-4 md:flex-row md:items-center">
                        <img
                          src={workerForm.portrait || DEFAULT_DRIVER_PORTRAIT}
                          alt="Worker profile preview"
                          className="h-20 w-20 rounded-xl border border-default object-cover"
                        />
                        <div className="flex-1">
                          <label className="block text-sm font-semibold text-primary">
                            {t("profile_picture")}
                          </label>
                          <p className="mt-1 text-sm text-secondary">
                            {t("profile_picture_description")}
                          </p>
                          <input
                            type="file"
                            accept="image/png"
                            onChange={handleWorkerPortraitUpload}
                            className="mt-3 block w-full text-sm text-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--color-accent-primary)] file:px-4 file:py-2 file:font-semibold file:text-white"
                          />
                        </div>
                      </div>
                    </div>
                    <div className="flex gap-3 md:col-span-2">
                      <button type="submit" className="btn btn-primary h-12 flex-1 px-4">
                        {editingWorkerId ? t("save_changes") : t("save_worker")}
                      </button>
                      <button
                        type="button"
                        onClick={resetWorkerEditor}
                        className="btn btn-secondary h-12 px-4"
                      >
                        {t("cancel")}
                      </button>
                    </div>
                  </form>
                ) : null}

                <div className="mt-4 max-h-[520px] space-y-3 overflow-y-auto pr-1">
                  {(() => {
                    const visibleWorkers = database.attendanceWorkers
                      .filter((worker) => worker.id !== editingWorkerId)
                      .filter(
                        (worker) =>
                          showInactiveWorkers || worker.isActive !== false,
                      );

                    if (database.attendanceWorkers.length === 0) {
                      return (
                        <div className="rounded-xl border border-dashed border-default bg-card px-5 py-6 text-sm text-secondary">
                          {t("no_workers_yet")}
                        </div>
                      );
                    }

                    if (visibleWorkers.length === 0) {
                      return (
                        <div className="rounded-xl border border-dashed border-default bg-card px-5 py-6 text-sm text-secondary">
                          All workers are inactive. Toggle &quot;Show inactive workers&quot; to reveal them.
                        </div>
                      );
                    }

                    return visibleWorkers.map((worker) => {
                      const isActive = worker.isActive !== false;
                      return (
                      <div
                        key={worker.id}
                        className={`rounded-2xl border border-default bg-card px-5 py-4 ${
                          isActive ? "" : "opacity-70"
                        }`}
                      >
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                          <div className="flex items-center gap-4">
                            <img
                              src={worker.portrait || DEFAULT_DRIVER_PORTRAIT}
                              alt={worker.name}
                              className="h-16 w-16 rounded-xl border border-default object-cover"
                            />
                            <div>
                              <p className="text-xl font-semibold leading-tight text-primary">
                                {worker.name}
                              </p>
                              <p className="mt-1 text-base leading-snug text-secondary">
                                {worker.badgeId || "No worker ID"}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {worker.shift ? (
                                  <span className="badge badge-info">{worker.shift}</span>
                                ) : null}
                                {worker.hasEmbedding ? (
                                  <span className="badge badge-success">
                                    Face Ready
                                    {worker.embeddingCount > 0
                                      ? ` (${worker.embeddingCount})`
                                      : ""}
                                  </span>
                                ) : (
                                  <span className="badge badge-warning">No Face Media</span>
                                )}
                                <span
                                  className={
                                    isActive ? "badge badge-success" : "badge badge-warning"
                                  }
                                >
                                  {isActive ? "Active" : "Inactive"}
                                </span>
                              </div>
                            </div>
                          </div>
                          <div className="ml-4 flex w-[148px] shrink-0 flex-col items-end gap-2">
                            <span className="rounded-full border border-default bg-surface px-3 py-1 text-xs text-secondary whitespace-nowrap">
                              {formatTimestamp(worker.addedAt)}
                            </span>
                            {worker.enrollmentPersonId ? (
                              <div className="flex w-full items-center justify-between gap-2 rounded-lg border border-default bg-surface px-2 py-1.5">
                                <span className="text-xs font-medium text-secondary">
                                  Active
                                </span>
                                <ToggleSwitch
                                  checked={isActive}
                                  onChange={() => handleToggleWorkerActive(worker)}
                                  ariaLabel={`Toggle active for ${worker.name}`}
                                />
                              </div>
                            ) : null}
                            <div className="flex w-full flex-col gap-1.5">
                              <button
                                type="button"
                                onClick={() => handleEditWorker(worker)}
                                className="btn btn-secondary h-8 w-full px-3 text-sm"
                              >
                                {t("edit")}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteWorker(worker.id)}
                                className="btn h-8 w-full px-3 text-sm text-white"
                                style={{
                                  backgroundColor: "var(--color-error)",
                                  borderColor: "transparent",
                                }}
                              >
                                {t("delete")}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                      );
                    });
                  })()}
                </div>
              </div>
              ) : null}
            </div>
          </motion.article>
          ) : null}
          </motion.section>

        <aside className="space-y-6">
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="panel"
          >
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <UsersIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <p className="eyebrow text-[10px]">{t("current_session")}</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    {t("account")}
                  </h2>
                </div>
              </div>
            </div>
            <div className="panel__content space-y-3">
              <div className="rounded-xl border border-default bg-surface px-5 py-4">
                <span className="text-secondary">{t("signed_in_email")}</span>
                <p className="mt-1 break-all font-semibold text-primary">
                  {signedInEmail}
                </p>
              </div>
              <div className="rounded-xl border border-default bg-surface px-5 py-4">
                <span className="text-secondary">{t("account_type")}</span>
                <p className="mt-1 font-semibold text-primary">{accountType}</p>
              </div>
              {supportHref ? (
                <a href={supportHref} className="btn btn-secondary h-12 w-full px-4">
                  {t("contact_dashboard_support")}
                  <ExternalLinkIcon size={16} />
                </a>
              ) : null}
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="panel"
          >
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <SettingsIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <p className="eyebrow text-[10px]">Security</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    Access & Recovery
                  </h2>
                </div>
              </div>
            </div>
            <div className="panel__content space-y-5">
              <div
                className="relative overflow-hidden rounded-[26px] border border-default bg-surface px-5 py-5"
                style={{
                  background:
                    "linear-gradient(180deg, rgba(8,145,178,0.06), rgba(15,23,42,0) 48%), var(--color-bg-surface)",
                }}
              >
                <div className="pointer-events-none absolute inset-0 opacity-60" />
                <div className="relative flex items-center justify-between gap-3">
                  <p className="eyebrow text-[10px]">Security Center</p>
                  <span className="text-xs font-medium text-secondary">Choose a workflow</span>
                </div>
                <div className="relative mt-4 grid gap-3 sm:grid-cols-2">
                  {[
                    {
                      key: SECURITY_PANELS.TWO_FACTOR,
                      title: "2FA",
                      subtitle: user?.two_factor_enabled
                        ? "Authenticator protection is enabled for this account."
                        : "Add a second sign-in step with an authenticator app.",
                    },
                    {
                      key: SECURITY_PANELS.PASSWORD,
                      title: "Password Reset",
                      subtitle: "Open the self-service password change process.",
                    },
                  ].map((panel) => {
                    const isActive = activeSecurityPanel === panel.key;
                    return (
                      <button
                        key={panel.key}
                        type="button"
                        onClick={() => setActiveSecurityPanel(panel.key)}
                        className="rounded-[22px] border px-5 py-5 text-left transition duration-200 hover:-translate-y-0.5"
                        style={{
                          borderColor: isActive
                            ? "var(--color-accent-primary)"
                            : "rgba(14, 165, 233, 0.24)",
                          background: isActive
                            ? "linear-gradient(135deg, rgba(8,145,178,0.3), rgba(14,165,233,0.1))"
                            : "linear-gradient(135deg, rgba(8,145,178,0.1), rgba(14,165,233,0.03))",
                          boxShadow: isActive
                            ? "0 18px 34px rgba(8, 145, 178, 0.14), inset 0 0 0 1px rgba(255,255,255,0.04)"
                            : "inset 0 0 0 1px rgba(255,255,255,0.02)",
                        }}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <span className="eyebrow text-[10px]">
                            {panel.key === SECURITY_PANELS.TWO_FACTOR ? "Sign-In Shield" : "Credential Flow"}
                          </span>
                          {isActive ? (
                            <span className="rounded-full border border-[var(--color-accent-primary)]/40 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-accent-primary)]">
                              Open
                            </span>
                          ) : null}
                        </div>
                        <p
                          className="mt-5 font-display text-[1.45rem] font-semibold"
                          style={{ color: "var(--color-accent-primary)" }}
                        >
                          {panel.title}
                        </p>
                        <p className="mt-2 max-w-[34ch] text-sm leading-6 text-secondary">
                          {panel.subtitle}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {activeSecurityPanel === SECURITY_PANELS.PASSWORD ? (
                <div className="rounded-2xl border border-default bg-surface px-5 py-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <p className="eyebrow text-[10px]">Password Reset</p>
                      <h3
                        className="mt-1 font-display text-2xl font-semibold"
                        style={{ color: "var(--color-accent-primary)" }}
                      >
                        Reset your password directly
                      </h3>
                      <p className="mt-2 max-w-2xl text-sm text-secondary">
                        No admin email is required. Confirm your current password, set a new one,
                        and this account updates immediately.
                      </p>
                    </div>
                    <span className="badge badge-info">Self-service</span>
                  </div>

                  {passwordMessage ? (
                    <div className="mt-5 rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                        {passwordMessage}
                      </p>
                    </div>
                  ) : null}

                  {passwordError ? (
                    <div className="mt-5 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                        {passwordError}
                      </p>
                    </div>
                  ) : null}

                  <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
                    <form className="space-y-3" onSubmit={handleChangePassword}>
                      <input
                        type="password"
                        value={passwordForm.current_password}
                        onChange={(event) => {
                          setPasswordForm((current) => ({
                            ...current,
                            current_password: event.target.value,
                          }));
                          setPasswordError("");
                        }}
                        className="input h-12"
                        placeholder="Current password"
                        autoComplete="current-password"
                      />
                      <input
                        type="password"
                        value={passwordForm.password}
                        onChange={(event) => {
                          setPasswordForm((current) => ({
                            ...current,
                            password: event.target.value,
                          }));
                          setPasswordError("");
                        }}
                        className="input h-12"
                        placeholder="New password"
                        autoComplete="new-password"
                      />
                      <input
                        type="password"
                        value={passwordForm.confirm_password}
                        onChange={(event) => {
                          setPasswordForm((current) => ({
                            ...current,
                            confirm_password: event.target.value,
                          }));
                          setPasswordError("");
                        }}
                        className="input h-12"
                        placeholder="Confirm new password"
                        autoComplete="new-password"
                      />
                      <PasswordStrength password={passwordForm.password} />
                      {passwordForm.confirm_password ? (
                        <p className={`text-sm font-semibold ${passwordsMatch ? "text-[var(--color-success)]" : "text-[var(--color-error)]"}`}>
                          {passwordsMatch ? "Passwords match." : "Passwords do not match."}
                        </p>
                      ) : null}
                      <button
                        type="submit"
                        disabled={passwordBusy}
                        className="btn btn-primary h-12 w-full px-4 disabled:opacity-60"
                      >
                        {passwordBusy ? "Updating password..." : "Update password"}
                      </button>
                    </form>

                    <div className="rounded-2xl border border-default bg-card px-5 py-5">
                      <p
                        className="font-display text-lg font-semibold"
                        style={{ color: "var(--color-accent-primary)" }}
                      >
                        Reset process
                      </p>
                      <div className="mt-4 space-y-4">
                        {[
                          "Enter your current password so the reset stays tied to this account.",
                          "Choose a stronger replacement and confirm it before submitting.",
                          "After the update, use the new password on your next sign-in.",
                        ].map((step, index) => (
                          <div key={step} className="flex items-start gap-3">
                            <span
                              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
                              style={{ backgroundColor: "var(--color-accent-primary)" }}
                            >
                              {index + 1}
                            </span>
                            <p className="pt-1 text-sm text-secondary">{step}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div
                  className="relative overflow-hidden rounded-[26px] border border-default bg-surface px-5 py-5"
                  style={{
                    background:
                      "radial-gradient(circle at top right, rgba(8,145,178,0.14), transparent 28%), var(--color-bg-surface)",
                  }}
                >
                  <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                    <div className="rounded-[22px] border border-default bg-card px-5 py-5">
                      <p className="eyebrow text-[10px]">2FA</p>
                      <h3
                        className="mt-2 font-display text-[1.9rem] font-semibold"
                        style={{ color: "var(--color-accent-primary)" }}
                      >
                        Authenticator protection
                      </h3>
                      <p className="mt-3 max-w-2xl text-sm leading-7 text-secondary">
                        Add an app-based confirmation code to sign-in so this account stays protected
                        even if the password is exposed.
                      </p>
                    </div>
                    <div
                      className="rounded-[22px] border px-4 py-4"
                      style={{
                        borderColor: user?.two_factor_enabled
                          ? "rgba(34,197,94,0.24)"
                          : "rgba(245,158,11,0.24)",
                        background: user?.two_factor_enabled
                          ? "linear-gradient(135deg, rgba(34,197,94,0.12), rgba(15,23,42,0.9))"
                          : "linear-gradient(135deg, rgba(245,158,11,0.12), rgba(15,23,42,0.9))",
                      }}
                    >
                      <p className="eyebrow text-[10px]">2FA Status</p>
                      <div className="mt-4">
                        <p
                          className="font-display text-[2.4rem] font-semibold leading-none"
                          style={{
                            color: user?.two_factor_enabled
                              ? "var(--color-success)"
                              : "var(--color-warning)",
                          }}
                        >
                          {user?.two_factor_enabled ? "ON" : "OFF"}
                        </p>
                      </div>
                    </div>
                  </div>

                  {twoFactorMessage ? (
                    <div className="mt-5 rounded-xl border border-[var(--color-success)] bg-[var(--color-success-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-success)" }}>
                        {twoFactorMessage}
                      </p>
                    </div>
                  ) : null}

                  {twoFactorError ? (
                    <div className="mt-5 rounded-xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-4 py-3">
                      <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
                        {twoFactorError}
                      </p>
                    </div>
                  ) : null}

                  {!user?.two_factor_enabled ? (
                    <>
                      <div className="mt-5 grid gap-3 md:grid-cols-3">
                        {[
                          {
                            title: "Generate setup",
                            detail: "Open the setup flow and create a fresh QR code for this account.",
                          },
                          {
                            title: "Scan the app",
                            detail: "Use Google Authenticator, Authy, or another TOTP app.",
                          },
                          {
                            title: "Confirm the code",
                            detail: "Enter the 6-digit code from the app to finish activation.",
                          },
                        ].map((step, index) => (
                          <div
                            key={step.title}
                            className="rounded-[22px] border border-default bg-card px-4 py-4"
                          >
                            <div className="flex items-center gap-3">
                              <span
                                className="flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold text-white"
                                style={{ backgroundColor: "var(--color-accent-primary)" }}
                              >
                                {index + 1}
                              </span>
                              <p className="text-sm font-semibold text-primary">{step.title}</p>
                            </div>
                            <p className="mt-3 text-sm leading-6 text-secondary">{step.detail}</p>
                          </div>
                        ))}
                      </div>

                      <div
                        className="mt-5 rounded-[22px] border border-default px-5 py-5"
                        style={{
                          background:
                            "linear-gradient(135deg, rgba(255,255,255,0.02), rgba(8,145,178,0.05))",
                        }}
                      >
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                          <div>
                            <p className="font-semibold text-primary">Authenticator setup</p>
                            <p className="mt-1 text-sm leading-6 text-secondary">
                              Generate or refresh the QR code, then verify the one-time code from
                              your app.
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={handleStartTwoFactorSetup}
                            disabled={twoFactorBusy}
                            className="btn btn-primary h-12 px-5 disabled:opacity-60"
                          >
                            {twoFactorSetup ? "Refresh QR code" : "Generate QR code"}
                          </button>
                        </div>

                        {twoFactorSetup ? (
                          <div className="mt-5 grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
                            <div className="rounded-[22px] border border-default bg-surface px-4 py-4">
                              <p className="text-sm font-semibold text-primary">Scan this QR code</p>
                              <img
                                src={twoFactorSetup.qr_code_data_url}
                                alt="Two-factor QR code"
                                className="mx-auto mt-4 h-56 w-56 rounded-xl border border-default bg-white object-contain p-3"
                              />
                            </div>

                            <div className="rounded-[22px] border border-default bg-surface px-5 py-5">
                              <p className="font-semibold text-primary">Confirm activation</p>
                              <p className="mt-1 text-sm text-secondary">
                                If scanning fails, you can still paste the secret link into your
                                authenticator app.
                              </p>
                              <p className="mt-3 break-all rounded-xl border border-default bg-card px-3 py-3 text-xs text-secondary">
                                {twoFactorSetup.otpauth_url}
                              </p>
                              <form className="mt-4 space-y-3" onSubmit={handleConfirmTwoFactorEnable}>
                                <input
                                  type="text"
                                  value={twoFactorEnableCode}
                                  onChange={(event) => setTwoFactorEnableCode(event.target.value)}
                                  placeholder="Enter 6-digit code"
                                  className="input h-12"
                                  inputMode="numeric"
                                />
                                <button
                                  type="submit"
                                  disabled={twoFactorBusy}
                                  className="btn btn-primary h-12 w-full px-4 disabled:opacity-60"
                                >
                                  Confirm and enable
                                </button>
                              </form>
                            </div>
                          </div>
                        ) : null}
                      </div>

                      {twoFactorBackupCodes.length > 0 ? (
                        <div className="mt-5 rounded-[22px] border border-default bg-card px-5 py-5">
                          <div className="flex items-start gap-3">
                            <CheckCircleIcon className="mt-0.5 h-5 w-5 text-[var(--color-success)]" />
                            <div>
                              <p className="font-semibold text-primary">Backup codes</p>
                              <p className="mt-1 text-sm text-secondary">
                                These recovery codes appear once. Save them somewhere secure before
                                leaving this screen.
                              </p>
                            </div>
                          </div>
                          <div className="mt-4 grid gap-2 sm:grid-cols-2">
                            {twoFactorBackupCodes.map((code) => (
                              <div
                                key={code}
                                className="rounded-lg border border-default bg-surface px-3 py-2 font-mono text-sm font-semibold text-primary"
                              >
                                {code}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
                      <div className="rounded-2xl border border-default bg-card px-5 py-5">
                        <p className="font-semibold text-primary">What 2FA changes</p>
                        <div className="mt-4 space-y-4">
                          {[
                            "Every sign-in asks for both your password and the live authenticator code.",
                            "Backup codes let you recover access if your authenticator device is unavailable.",
                            "To turn 2FA off, confirm your current password and a fresh authenticator code.",
                          ].map((line, index) => (
                            <div key={line} className="flex items-start gap-3">
                              <span
                                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
                                style={{ backgroundColor: "var(--color-accent-primary)" }}
                              >
                                {index + 1}
                              </span>
                              <p className="pt-1 text-sm text-secondary">{line}</p>
                            </div>
                          ))}
                        </div>

                        {twoFactorBackupCodes.length > 0 ? (
                          <div className="mt-5 rounded-2xl border border-default bg-surface px-4 py-4">
                            <p className="font-semibold text-primary">Latest backup codes</p>
                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                              {twoFactorBackupCodes.map((code) => (
                                <div
                                  key={code}
                                  className="rounded-lg border border-default bg-card px-3 py-2 font-mono text-sm font-semibold text-primary"
                                >
                                  {code}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>

                      <form
                        className="rounded-2xl border border-default bg-card px-5 py-5"
                        onSubmit={handleDisableTwoFactor}
                      >
                        <p className="eyebrow text-[10px]">Disable 2FA</p>
                        <p
                          className="mt-1 font-display text-xl font-semibold"
                          style={{ color: "var(--color-accent-primary)" }}
                        >
                          Confirm before removing protection
                        </p>
                        <p className="mt-2 text-sm text-secondary">
                          Enter your current password and a valid code from the authenticator app.
                        </p>
                        <div className="mt-4 space-y-3">
                          <input
                            type="password"
                            value={twoFactorDisableForm.current_password}
                            onChange={(event) =>
                              setTwoFactorDisableForm((current) => ({
                                ...current,
                                current_password: event.target.value,
                              }))
                            }
                            placeholder="Current password"
                            className="input h-12"
                          />
                          <input
                            type="text"
                            value={twoFactorDisableForm.code}
                            onChange={(event) =>
                              setTwoFactorDisableForm((current) => ({
                                ...current,
                                code: event.target.value,
                              }))
                            }
                            placeholder="Authenticator code"
                            className="input h-12"
                            inputMode="numeric"
                          />
                          <button
                            type="submit"
                            disabled={twoFactorBusy}
                            className="btn btn-secondary h-12 w-full px-4 disabled:opacity-60"
                          >
                            Disable 2FA
                          </button>
                        </div>
                      </form>
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.section>

          {isAdmin ? (
            <motion.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35 }}
              className="panel relative overflow-hidden"
            >
              <div
                className="pointer-events-none absolute inset-0"
                style={{
                  background:
                    "radial-gradient(ellipse at 50% 0%, var(--color-success-muted), transparent 50%)",
                }}
              />
              <div className="panel__header relative">
                <div>
                  <p className="eyebrow text-[10px]">System Health</p>
                  <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                    {t("core_services")}
                  </h2>
                </div>
              </div>
              <div className="panel__content relative space-y-3">
                {coreServices.map((service) => (
                  <div
                    key={service.label}
                    className="rounded-xl border border-default bg-surface px-5 py-4"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-secondary">{service.label}</span>
                      <div className="flex items-center gap-2">
                        <span
                          className="status-dot"
                          style={{
                            backgroundColor: variantColors[service.variant],
                          }}
                        />
                        <span
                          className="text-sm font-semibold"
                          style={{ color: variantColors[service.variant] }}
                        >
                          {service.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

export default Settings;
