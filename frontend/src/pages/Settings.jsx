import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
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
import { readSessionOperator } from "../utils/sessionOperator";
import {
  DEFAULT_DRIVER_PORTRAIT,
  readTestDatabase,
  writeTestDatabase,
} from "../utils/testDatabase";

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

const accessLevelLabels = {
  "site-operator": "Site operator",
  "regional-supervisor": "Regional supervisor",
  "security-admin": "Security admin",
};

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

const supportEmail = "ENV_SUPPORT_EMAIL";

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

function createWorkerFormTemplate(defaultCamera, drivers, worker) {
  return {
    name: worker?.name || "",
    badgeId: worker?.badgeId || "",
    shift: worker?.shift || drivers[0]?.shift || "",
    camera: worker?.camera || defaultCamera,
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
  const { darkMode, toggleDarkMode } = useThemePreference();
  const { t } = useAppLanguage();
  const [settings, setSettings] = useState(readAppSettings);
  const [database, setDatabase] = useState(readTestDatabase);
  const [driverForm, setDriverForm] = useState(() =>
    createDriverFormTemplate(readTestDatabase()),
  );
  const [workerForm, setWorkerForm] = useState(() =>
    createWorkerFormTemplate(
      readAppSettings().attendanceCamera,
      readTestDatabase().drivers,
    ),
  );
  const [showDriverForm, setShowDriverForm] = useState(false);
  const [showWorkerForm, setShowWorkerForm] = useState(false);
  const [editingDriverId, setEditingDriverId] = useState(null);
  const [editingWorkerId, setEditingWorkerId] = useState(null);
  const [workerSuccessPrompt, setWorkerSuccessPrompt] = useState(null);

  useEffect(() => {
    writeAppSettings(settings);
  }, [settings]);

  useEffect(() => {
    writeTestDatabase(database);
  }, [database]);

  const sessionOperator = readSessionOperator();
  const signedInEmail = sessionOperator.email || "No email stored for this session";
  const accountType =
    accessLevelLabels[settings.accessLevel] || "Authorized operator";
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

  const handleAddWorker = (event) => {
    event.preventDefault();

    if (!workerForm.name.trim() || !workerForm.badgeId.trim()) {
      return;
    }

    const isNewWorker = !editingWorkerId;
    const currentWorker = database.attendanceWorkers.find(
      (worker) => worker.id === editingWorkerId,
    );
    const nextWorker = {
      id: editingWorkerId || createDatabaseId("worker"),
      name: workerForm.name.trim(),
      badgeId: workerForm.badgeId.trim(),
      shift: workerForm.shift,
      camera: workerForm.camera,
      portrait: workerForm.portrait || DEFAULT_DRIVER_PORTRAIT,
      addedAt: currentWorker?.addedAt || new Date().toISOString(),
    };

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
      createWorkerFormTemplate(settings.attendanceCamera, database.drivers),
    );
    setShowWorkerForm(false);
    setEditingWorkerId(null);
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
    setWorkerSuccessPrompt(null);
    setEditingWorkerId(worker.id);
    setWorkerForm(
      createWorkerFormTemplate(
        settings.attendanceCamera,
        database.drivers,
        worker,
      ),
    );
    setShowWorkerForm(true);
  };

  const resetWorkerEditor = () => {
    setWorkerForm(
      createWorkerFormTemplate(settings.attendanceCamera, database.drivers),
    );
    setShowWorkerForm(false);
    setEditingWorkerId(null);
  };

  const handleDeleteWorker = (workerId) => {
    setDatabase((current) => ({
      ...current,
      attendanceWorkers: current.attendanceWorkers.filter(
        (worker) => worker.id !== workerId,
      ),
    }));

    if (editingWorkerId === workerId) {
      resetWorkerEditor();
    }
  };

  const resetPasswordHref = `mailto:${supportEmail}?subject=${encodeURIComponent(
    "Password reset request",
  )}&body=${encodeURIComponent(
    `Please reset the password for ${sessionOperator.email || "the current account"}.`,
  )}`;

  const supportHref = `mailto:${supportEmail}?subject=${encodeURIComponent(
    "Dashboard support request",
  )}&body=${encodeURIComponent(
    `I need dashboard support for the account ${sessionOperator.email || "in this browser session"}.`,
  )}`;

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">{t("platform_configuration")}</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          {t("settings")}
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
                  {t("workspace_controls")}
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

          <motion.article variants={itemVariants} className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <DriversIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <h2 className="font-display text-xl font-semibold text-primary">
                    {t("fleet_monitoring")}
                  </h2>
                  <p className="mt-1 text-sm text-secondary">
                    {database.drivers.length} driver
                    {database.drivers.length === 1 ? "" : "s"} stored locally.
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
                    database.drivers.map((driver) => (
                      <div
                        key={driver.id}
                        className="rounded-xl border border-default bg-card px-5 py-2.5"
                      >
                        <div className="flex flex-col gap-1.5 md:flex-row md:items-start md:justify-between">
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
                            </div>
                          </div>
                          <div className="ml-4 flex w-[104px] shrink-0 flex-col items-end gap-2">
                            <span className="text-xs text-secondary whitespace-nowrap">
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
                        <p className="mt-1.5 text-base leading-snug text-secondary">
                          {[driver.assignedRoute, driver.shift].filter(Boolean).join(" • ")}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </motion.article>

          <motion.article variants={itemVariants} className="panel">
            <div className="panel__header">
              <div className="flex items-center gap-3">
                <AttendanceIcon className="h-5 w-5 text-[var(--color-accent-primary)]" />
                <div>
                  <h2 className="font-display text-xl font-semibold text-primary">
                    {t("attendance_ppe")}
                  </h2>
                  <p className="mt-1 text-sm text-secondary">
                    {database.attendanceWorkers.length} worker
                    {database.attendanceWorkers.length === 1 ? "" : "s"} stored locally.
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

              <div className="rounded-xl border border-default bg-surface px-5 py-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="font-semibold text-primary">{t("worker_database")}</p>
                    <p className="mt-1 text-sm text-secondary">
                      {t("worker_database_description")}
                    </p>
                  </div>
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
                      setWorkerForm(
                        createWorkerFormTemplate(
                          settings.attendanceCamera,
                          database.drivers,
                        ),
                      );
                    }}
                    className="btn btn-secondary h-11 px-4"
                  >
                    {t("add_worker")}
                  </button>
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
                    <select
                      value={workerForm.camera}
                      onChange={(event) =>
                        setWorkerForm((current) => ({
                          ...current,
                          camera: event.target.value,
                        }))
                      }
                      className="input h-12"
                    >
                      {attendanceCameraOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
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

                <div className="mt-4 space-y-3">
                  {database.attendanceWorkers.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-default bg-card px-5 py-6 text-sm text-secondary">
                      {t("no_workers_yet")}
                    </div>
                  ) : (
                    database.attendanceWorkers.map((worker) => (
                      <div
                        key={worker.id}
                        className="rounded-xl border border-default bg-card px-5 py-2.5"
                      >
                        <div className="flex flex-col gap-1.5 lg:flex-row lg:items-start lg:justify-between">
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
                            </div>
                          </div>
                          <div className="ml-4 flex w-[104px] shrink-0 flex-col items-end gap-2">
                            <span className="text-xs text-secondary whitespace-nowrap">
                              {formatTimestamp(worker.addedAt)}
                            </span>
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
                        <p className="mt-1.5 text-base leading-snug text-secondary">
                          {[
                            worker.shift,
                            attendanceCameraOptions.find(
                              (option) => option.value === worker.camera,
                            )?.label,
                          ]
                            .filter(Boolean)
                            .join(" • ")}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </motion.article>
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
              <a
                href={resetPasswordHref}
                className="btn btn-secondary h-12 w-full px-4"
              >
                {t("reset_password")}
                <ExternalLinkIcon size={16} />
              </a>
              <a href={supportHref} className="btn btn-secondary h-12 w-full px-4">
                {t("contact_dashboard_support")}
                <ExternalLinkIcon size={16} />
              </a>
            </div>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
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
        </aside>
      </div>
    </div>
  );
}

export default Settings;
