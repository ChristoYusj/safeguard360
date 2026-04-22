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

  it("keeps denied PPE reviews on the worker roster even when no attendance record is created", () => {
    const { rosterCards } = buildAttendanceSessionState({
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

    expect(rosterCards).toHaveLength(1);
    expect(rosterCards[0].registeredViolations).toHaveLength(1);
    expect(rosterCards[0].registeredViolations[0]).toMatchObject({
      id: "review:review-2",
      decision: "Entry denied",
      summary: "PPE status could not be confirmed automatically.",
    });
  });

  it("populates the latest checkout details for workers who have already left the site", () => {
    const { rosterCards } = buildAttendanceSessionState({
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

    expect(rosterCards).toHaveLength(1);
    expect(rosterCards[0].latestCheckIn).toMatchObject({
      id: "attendance-entry-3",
      logMethod: "AUTO",
    });
    expect(rosterCards[0].latestCheckOut).toMatchObject({
      id: "attendance-exit-3",
      logMethod: "AUTO",
    });
  });
});
