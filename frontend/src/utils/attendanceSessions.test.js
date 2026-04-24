import { describe, it, expect } from "vitest";

import {
  buildAttendanceSessionState,
  getShiftIdForTimestamp,
} from "./attendanceSessions";

describe("getShiftIdForTimestamp", () => {
  const atHour = (hour) => {
    const d = new Date();
    d.setHours(hour, 0, 0, 0);
    return d.toISOString();
  };

  it("returns null for falsy timestamp", () => {
    expect(getShiftIdForTimestamp(null)).toBeNull();
    expect(getShiftIdForTimestamp("")).toBeNull();
    expect(getShiftIdForTimestamp(undefined)).toBeNull();
  });

  it("maps morning hours to day shift", () => {
    expect(getShiftIdForTimestamp(atHour(6))).toBe("day");
    expect(getShiftIdForTimestamp(atHour(10))).toBe("day");
    expect(getShiftIdForTimestamp(atHour(13))).toBe("day");
  });

  it("maps afternoon hours to swing shift", () => {
    expect(getShiftIdForTimestamp(atHour(14))).toBe("swing");
    expect(getShiftIdForTimestamp(atHour(18))).toBe("swing");
    expect(getShiftIdForTimestamp(atHour(21))).toBe("swing");
  });

  it("maps late night and early morning to night shift", () => {
    expect(getShiftIdForTimestamp(atHour(22))).toBe("night");
    expect(getShiftIdForTimestamp(atHour(23))).toBe("night");
    expect(getShiftIdForTimestamp(atHour(0))).toBe("night");
    expect(getShiftIdForTimestamp(atHour(5))).toBe("night");
  });

  it("boundary: 14:00 is swing, not day", () => {
    expect(getShiftIdForTimestamp(atHour(14))).toBe("swing");
  });

  it("boundary: 22:00 is night, not swing", () => {
    expect(getShiftIdForTimestamp(atHour(22))).toBe("night");
  });
});

describe("buildAttendanceSessionState", () => {
  it("moves approved PPE override violations onto the worker roster without duplicating them", () => {
    const timestamp = "2026-04-22T07:10:00.000Z";
    const decidedAt = "2026-04-22T07:11:00.000Z";

    const { rosterCards } = buildAttendanceSessionState({
      persons: [
        {
          id: "worker-1",
          name: "Alex Carter",
          employee_id: "EMP-100",
          shift_id: "day",
          is_active: true,
        },
      ],
      attendanceRecords: [
        {
          id: "attendance-1",
          person_id: "worker-1",
          person_name: "Alex Carter",
          person_employee_id: "EMP-100",
          direction: "ENTRY",
          timestamp,
          access_granted: true,
          ppe_compliant: false,
          confidence: 0.91,
          snapshot_path: "snapshots/review-1.jpg",
          ppe_details: {
            status: "non_compliant",
            required_items: ["helmet", "vest"],
            missing_items: ["helmet"],
            override_used: true,
            override_reason_type: "ppe_non_compliance",
          },
          log_method: "MANUAL",
        },
      ],
      gateReviews: [
        {
          id: "review-1",
          person_id: "worker-1",
          person_name: "Alex Carter",
          person_employee_id: "EMP-100",
          suggested_direction: "ENTRY",
          confidence: 0.91,
          timestamp,
          decided_at: decidedAt,
          status: "APPROVED",
          snapshot_path: "snapshots/review-1.jpg",
          review_reasons: ["missing_helmet"],
          ppe_details: {
            status: "non_compliant",
            required_items: ["helmet", "vest"],
            missing_items: ["helmet"],
            override_used: true,
            override_reason_type: "ppe_non_compliance",
          },
        },
      ],
    });

    expect(rosterCards).toHaveLength(1);
    expect(rosterCards[0].registeredViolations).toHaveLength(1);
    expect(rosterCards[0].registeredViolations[0]).toMatchObject({
      id: "review:review-1",
      decision: "Override granted",
      summary: "Missing helmet",
    });
  });

  it("keeps approved PPE override check-ins visible when the worker has no assigned shift", () => {
    const timestamp = "2026-04-22T23:10:00.000Z";
    const { activeSessions, rosterCards } = buildAttendanceSessionState({
      persons: [
        {
          id: "worker-no-shift",
          name: "Christo",
          employee_id: "EMP-360",
          shift_id: null,
          is_active: true,
        },
      ],
      attendanceRecords: [
        {
          id: "attendance-no-shift",
          person_id: "worker-no-shift",
          person_name: "Christo",
          person_employee_id: "EMP-360",
          direction: "ENTRY",
          timestamp,
          access_granted: true,
          ppe_compliant: false,
          confidence: 0.9,
          ppe_details: {
            status: "non_compliant",
            required_items: ["helmet", "vest"],
            missing_items: ["vest"],
            override_used: true,
            override_reason_type: "ppe_non_compliance",
          },
          log_method: "MANUAL",
        },
      ],
      gateReviews: [],
    });

    expect(activeSessions).toHaveLength(1);
    expect(activeSessions[0]).toMatchObject({
      personId: "worker-no-shift",
      shiftId: null,
    });
    expect(rosterCards).toHaveLength(1);
    expect(rosterCards[0]).toMatchObject({
      personId: "worker-no-shift",
      shiftId: null,
    });
    expect(rosterCards[0].registeredViolations).toHaveLength(1);
    expect(rosterCards[0].registeredViolations[0]).toMatchObject({
      id: "attendance:attendance-no-shift",
      summary: "Missing vest",
    });
  });

  it("does not keep resolved denied reviews in the active roster when no cycle is open", () => {
    const { rosterCards, completedSessions } = buildAttendanceSessionState({
      persons: [
        {
          id: "worker-2",
          name: "Jamie Lin",
          employee_id: "EMP-200",
          shift_id: "day",
          is_active: true,
        },
      ],
      attendanceRecords: [],
      gateReviews: [
        {
          id: "review-2",
          person_id: "worker-2",
          person_name: "Jamie Lin",
          person_employee_id: "EMP-200",
          suggested_direction: "ENTRY",
          confidence: 0.88,
          timestamp: "2026-04-22T08:00:00.000Z",
          decided_at: "2026-04-22T08:01:00.000Z",
          status: "DENIED",
          review_reasons: ["uncertain_ppe"],
          ppe_details: {
            status: "uncertain",
            required_items: ["helmet", "vest"],
            missing_items: [],
            override_used: false,
          },
        },
      ],
    });

    expect(rosterCards).toHaveLength(0);
    expect(completedSessions).toHaveLength(0);
  });

  it("moves a finished check-in plus check-out into completed sessions and clears the active roster", () => {
    const { rosterCards, completedSessions } = buildAttendanceSessionState({
      persons: [
        {
          id: "worker-3",
          name: "Morgan Vale",
          employee_id: "EMP-300",
          shift_id: "day",
          is_active: true,
        },
      ],
      attendanceRecords: [
        {
          id: "attendance-entry-3",
          person_id: "worker-3",
          person_name: "Morgan Vale",
          person_employee_id: "EMP-300",
          direction: "ENTRY",
          timestamp: "2026-04-22T06:45:00.000Z",
          access_granted: true,
          ppe_compliant: true,
          confidence: 0.95,
          ppe_details: {
            status: "compliant",
            required_items: ["helmet", "vest"],
            missing_items: [],
          },
          log_method: "AUTO",
        },
        {
          id: "attendance-exit-3",
          person_id: "worker-3",
          person_name: "Morgan Vale",
          person_employee_id: "EMP-300",
          direction: "EXIT",
          timestamp: "2026-04-22T12:05:00.000Z",
          access_granted: true,
          ppe_compliant: true,
          confidence: 0.94,
          ppe_details: {
            status: "skipped",
            required_items: [],
            missing_items: [],
          },
          log_method: "AUTO",
        },
      ],
      gateReviews: [],
    });

    expect(rosterCards).toHaveLength(0);
    expect(completedSessions).toHaveLength(1);
    expect(completedSessions[0].checkIn).toMatchObject({
      id: "attendance-entry-3",
      log_method: "AUTO",
    });
    expect(completedSessions[0].checkOut).toMatchObject({
      id: "attendance-exit-3",
      log_method: "AUTO",
    });
  });

  it("keeps only the newest open cycle in the roster after an older cycle was completed", () => {
    const { rosterCards, completedSessions } = buildAttendanceSessionState({
      persons: [
        {
          id: "worker-4",
          name: "Taylor Brooks",
          employee_id: "EMP-400",
          shift_id: "day",
          is_active: true,
        },
      ],
      attendanceRecords: [
        {
          id: "attendance-entry-4a",
          person_id: "worker-4",
          person_name: "Taylor Brooks",
          person_employee_id: "EMP-400",
          direction: "ENTRY",
          timestamp: "2026-04-22T06:30:00.000Z",
          access_granted: true,
          ppe_compliant: true,
          confidence: 0.95,
          ppe_details: {
            status: "compliant",
            required_items: ["helmet", "vest"],
            missing_items: [],
          },
          log_method: "AUTO",
        },
        {
          id: "attendance-exit-4a",
          person_id: "worker-4",
          person_name: "Taylor Brooks",
          person_employee_id: "EMP-400",
          direction: "EXIT",
          timestamp: "2026-04-22T11:30:00.000Z",
          access_granted: true,
          ppe_compliant: true,
          confidence: 0.94,
          ppe_details: {
            status: "skipped",
            required_items: [],
            missing_items: [],
          },
          log_method: "AUTO",
        },
        {
          id: "attendance-entry-4b",
          person_id: "worker-4",
          person_name: "Taylor Brooks",
          person_employee_id: "EMP-400",
          direction: "ENTRY",
          timestamp: "2026-04-22T12:00:00.000Z",
          access_granted: true,
          ppe_compliant: true,
          confidence: 0.96,
          ppe_details: {
            status: "compliant",
            required_items: ["helmet", "vest"],
            missing_items: [],
          },
          log_method: "AUTO",
        },
      ],
      gateReviews: [],
    });

    expect(completedSessions).toHaveLength(1);
    expect(rosterCards).toHaveLength(1);
    expect(rosterCards[0].latestCheckIn).toMatchObject({
      id: "attendance-entry-4b",
    });
    expect(rosterCards[0].latestCheckOut).toBeNull();
  });
});
