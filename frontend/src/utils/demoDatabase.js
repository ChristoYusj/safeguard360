const STORAGE_KEY = "safeguard360-test-database";
export const TEST_DATABASE_UPDATED_EVENT = "safeguard360:test-database-updated";
export const DEFAULT_DRIVER_PORTRAIT = `data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240">
    <rect width="240" height="240" fill="#eeeeee"/>
    <circle cx="120" cy="82" r="42" fill="#b6bac1"/>
    <path d="M28 208c10-43 43-72 92-72 49 0 82 29 92 72H28Z" fill="#b6bac1"/>
  </svg>`,
)}`;

const DEFAULT_DRIVER_RECORDS = [
  {
    id: "drv-christopher",
    name: "Christopher Yazigi",
    fullName: "Christopher Yazigi",
    vehicle: "TRK-4712",
    truckId: "TRK-4712",
    stateId: "LB-3914-7726",
    role: "Senior Transport Operator",
    licenseClass: "C1E",
    assignedRoute: "BRT-12 - Beirut North",
    shift: "Day Shift (06:00 - 14:00)",
    destinationKey: "beirut",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2024Drivers/verstappen.png.img.512.medium.png",
    addedAt: "2026-03-28T06:00:00.000Z",
  },
  {
    id: "drv-rami",
    name: "Rami Nassar",
    fullName: "Rami Nassar",
    vehicle: "TRK-5824",
    truckId: "TRK-5824",
    stateId: "LB-5521-1840",
    role: "Regional Fleet Operator",
    licenseClass: "C1E",
    assignedRoute: "NTH-04 - Tripoli Cargo Link",
    shift: "Mid Shift (10:00 - 18:00)",
    destinationKey: "tripoli",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2024Drivers/leclerc.png.img.512.medium.png",
    addedAt: "2026-03-28T06:05:00.000Z",
  },
  {
    id: "drv-karim",
    name: "Karim Haddad",
    fullName: "Karim Haddad",
    vehicle: "TRK-6031",
    truckId: "TRK-6031",
    stateId: "LB-8802-4419",
    role: "Urban Safety Driver",
    licenseClass: "C1E",
    assignedRoute: "ACH-09 - Ashrafieh Core",
    shift: "Late Shift (14:00 - 22:00)",
    destinationKey: "achrafieh",
    portrait:
      "https://media.formula1.com/content/dam/fom-website/drivers/2025Drivers/hamilton.png.img.512.medium.png",
    addedAt: "2026-03-28T06:10:00.000Z",
  },
];

const DEFAULT_DEMO_DATABASE = {
  schemaVersion: 3,
  drivers: DEFAULT_DRIVER_RECORDS,
  attendanceWorkers: [],
  driverOptionHistory: {
    roles: [],
    assignedRoutes: [],
    shifts: [],
    destinationKeys: [],
  },
};

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))];
}

function buildDriverOptionHistory(drivers = [], history = {}) {
  return {
    roles: uniqueValues([
      ...DEFAULT_DRIVER_RECORDS.map((driver) => driver.role),
      ...(history.roles || []),
      ...drivers.map((driver) => driver?.role),
    ]),
    assignedRoutes: uniqueValues([
      ...DEFAULT_DRIVER_RECORDS.map((driver) => driver.assignedRoute),
      ...(history.assignedRoutes || []),
      ...drivers.map((driver) => driver?.assignedRoute),
    ]),
    shifts: uniqueValues([
      ...DEFAULT_DRIVER_RECORDS.map((driver) => driver.shift),
      ...(history.shifts || []),
      ...drivers.map((driver) => driver?.shift),
    ]),
    destinationKeys: uniqueValues([
      ...DEFAULT_DRIVER_RECORDS.map((driver) => driver.destinationKey),
      ...(history.destinationKeys || []),
      ...drivers.map((driver) => driver?.destinationKey),
    ]),
  };
}

function normalizeDriver(driver, index) {
  const fallbackNumber = String(index + 1).padStart(4, "0");
  const fallbackName = driver?.fullName || driver?.name || `Driver ${index + 1}`;
  const fallbackTruckId = driver?.truckId || driver?.vehicle || `TRK-${fallbackNumber}`;

  return {
    id: driver?.id || `driver-${fallbackNumber}`,
    name: driver?.name || fallbackName,
    fullName: driver?.fullName || fallbackName,
    vehicle: driver?.vehicle || fallbackTruckId,
    truckId: fallbackTruckId,
    stateId: driver?.stateId || "Pending ID",
    role: driver?.role || "Fleet Driver",
    licenseClass: driver?.licenseClass || "Pending",
    assignedRoute: driver?.assignedRoute || "Route pending",
    shift: driver?.shift || "Schedule pending",
    destinationKey: driver?.destinationKey || "beirut",
    portrait: driver?.portrait || DEFAULT_DRIVER_PORTRAIT,
    addedAt: driver?.addedAt || new Date().toISOString(),
  };
}

function normalizeAttendanceWorker(worker, index) {
  const fallbackNumber = String(index + 1).padStart(4, "0");

  return {
    id: worker?.id || `worker-${fallbackNumber}`,
    name: worker?.name || `Worker ${index + 1}`,
    badgeId: worker?.badgeId || "",
    role: worker?.role || "Site Operator",
    assignedRoute: worker?.assignedRoute || "Route pending",
    shift: worker?.shift || "Schedule pending",
    destinationKey: worker?.destinationKey || "beirut",
    camera: worker?.camera || "webcam-0",
    portrait: worker?.portrait || DEFAULT_DRIVER_PORTRAIT,
    addedAt: worker?.addedAt || new Date().toISOString(),
  };
}

function normalizeDemoDatabase(database = {}) {
  const shouldSeedLegacyDrivers =
    database.schemaVersion == null &&
    Array.isArray(database.drivers) &&
    database.drivers.length === 0;

  const rawDrivers = Array.isArray(database.drivers)
    ? shouldSeedLegacyDrivers
      ? DEFAULT_DRIVER_RECORDS
      : database.drivers
    : DEFAULT_DRIVER_RECORDS;

  const rawWorkers = Array.isArray(database.attendanceWorkers)
    ? database.attendanceWorkers
    : [];

  return {
    schemaVersion: 3,
    drivers: rawDrivers.map(normalizeDriver),
    attendanceWorkers: rawWorkers.map(normalizeAttendanceWorker),
    driverOptionHistory: buildDriverOptionHistory(
      rawDrivers,
      database.driverOptionHistory,
    ),
  };
}

export function readTestDatabase() {
  if (typeof window === "undefined") {
    return normalizeDemoDatabase(DEFAULT_DEMO_DATABASE);
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return normalizeDemoDatabase(DEFAULT_DEMO_DATABASE);
    }

    return normalizeDemoDatabase(JSON.parse(raw));
  } catch (error) {
    console.error("[demoDatabase] Failed to read storage", error);
    return normalizeDemoDatabase(DEFAULT_DEMO_DATABASE);
  }
}

export function writeTestDatabase(database) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const normalizedDatabase = normalizeDemoDatabase(database);
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(normalizedDatabase),
    );
    window.dispatchEvent(new Event(TEST_DATABASE_UPDATED_EVENT));
  } catch (error) {
    console.error("[demoDatabase] Failed to write storage", error);
  }
}
