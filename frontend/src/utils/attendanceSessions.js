const SHIFT_BLOCKS = [
  {
    id: "day",
    startHour: 6,
    endHour: 14,
  },
  {
    id: "swing",
    startHour: 14,
    endHour: 22,
  },
  {
    id: "night",
    startHour: 22,
    endHour: 6,
  },
];

function normalizePpeDetails(details) {
  return {
    status: "not_evaluated",
    required_items: [],
    detected_items: [],
    missing_items: [],
    detector_confidences: {},
    override_used: false,
    override_reason_type: null,
    detector_available: false,
    detector_message: null,
    ...(details || {}),
  };
}

function normalizeReviewReasons(review) {
  return Array.isArray(review?.review_reasons) ? review.review_reasons : [];
}

function formatPpeReviewNote(review) {
  const ppeDetails = normalizePpeDetails(review?.ppe_details);
  const reviewReasons = normalizeReviewReasons(review);
  const missingItems = ppeDetails.missing_items || [];

  if (missingItems.length > 0) {
    return `Missing ${missingItems.join(", ")} required PPE.`;
  }
  if (reviewReasons.includes("uncertain_ppe")) {
    return "PPE status could not be confirmed automatically.";
  }
  return (
    review?.decision_note ||
    "Low-confidence recognition required operator review."
  );
}

function usesManualOverride(record, matchedReview) {
  return record?.log_method === "MANUAL" || Boolean(matchedReview);
}

function buildManualOverrideDetail(record, matchedReview, directionLabel) {
  const detailSource = matchedReview || null;
  const reviewPpeDetails = normalizePpeDetails(
    detailSource?.ppe_details || record?.ppe_details,
  );

  return {
    direction: directionLabel,
    decision: "Accepted",
    decidedAt:
      detailSource?.decided_at ||
      detailSource?.timestamp ||
      record?.timestamp ||
      null,
    decidedBy: detailSource?.decided_by || "Authorized operator",
    note: detailSource
      ? formatPpeReviewNote(detailSource)
      : "Operator approved a manual attendance review.",
    confidence: detailSource?.confidence ?? record?.confidence ?? null,
    reviewReasons: normalizeReviewReasons(detailSource),
    ppeDetails: reviewPpeDetails,
  };
}

function toTimestamp(value) {
  if (!value) {
    return 0;
  }

  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

export function getShiftIdForTimestamp(timestamp) {
  if (!timestamp) {
    return null;
  }

  const date = new Date(timestamp);
  const hour = date.getHours();

  if (hour >= SHIFT_BLOCKS[0].startHour && hour < SHIFT_BLOCKS[0].endHour) {
    return "day";
  }
  if (hour >= SHIFT_BLOCKS[1].startHour && hour < SHIFT_BLOCKS[1].endHour) {
    return "swing";
  }
  return "night";
}

function findMatchingApprovedReview(record, approvedReviews, usedReviewIds) {
  const candidates = approvedReviews.filter((review) => {
    if (usedReviewIds.has(review.id)) {
      return false;
    }
    if (review.person_id !== record.person_id) {
      return false;
    }
    if (review.suggested_direction !== record.direction) {
      return false;
    }
    return true;
  });

  if (candidates.length === 0) {
    return null;
  }

  const exactSnapshotMatch = candidates.find(
    (review) =>
      review.snapshot_path &&
      record.snapshot_path &&
      review.snapshot_path === record.snapshot_path,
  );

  if (exactSnapshotMatch) {
    usedReviewIds.add(exactSnapshotMatch.id);
    return exactSnapshotMatch;
  }

  const nearestReview = [...candidates].sort((left, right) => {
    const leftDelta = Math.abs(
      toTimestamp(left.decided_at || left.timestamp) - toTimestamp(record.timestamp),
    );
    const rightDelta = Math.abs(
      toTimestamp(right.decided_at || right.timestamp) - toTimestamp(record.timestamp),
    );
    return leftDelta - rightDelta;
  })[0];

  if (!nearestReview) {
    return null;
  }

  usedReviewIds.add(nearestReview.id);
  return nearestReview;
}

function createSessionShell(record, personsById) {
  const person = record.person_id ? personsById.get(record.person_id) : null;
  const resolvedShiftId = person?.shift_id || getShiftIdForTimestamp(record.timestamp);

  return {
    id: `session-${record.id}`,
    personId: record.person_id || null,
    personName: record.person_name || person?.name || "Unknown worker",
    employeeId: record.person_employee_id || person?.employee_id || null,
    shiftId: resolvedShiftId,
    checkIn: null,
    checkOut: null,
    hasManualOverride: false,
    manualOverrideDirections: [],
    manualOverrideDetails: [],
    ppeDetails: {
      checkIn: normalizePpeDetails(record.ppe_details),
      checkOut: normalizePpeDetails(null),
    },
  };
}

function buildRosterEvent(record, personsById, matchedReview) {
  const person = record.person_id ? personsById.get(record.person_id) : null;
  const resolvedShiftId = person?.shift_id || getShiftIdForTimestamp(record.timestamp);

  return {
    id: record.id,
    personId: record.person_id || null,
    personName: record.person_name || person?.name || "Unknown worker",
    employeeId: record.person_employee_id || person?.employee_id || null,
    shiftId: resolvedShiftId,
    timestamp: record.timestamp || null,
    confidence: record.confidence ?? matchedReview?.confidence ?? null,
    ppeDetails: normalizePpeDetails(record.ppe_details),
    cameraSourceType: record.camera_source_type || null,
    cameraSourceId: record.camera_source_id || null,
    logMethod:
      record.log_method ||
      (matchedReview ? "MANUAL" : "AUTO"),
    manualOverrideReview: matchedReview || null,
  };
}

function createEmptyRosterCard(person) {
  return {
    id: person?.id || `person-name:${person?.name || "unknown"}`,
    personId: person?.id || null,
    personName: person?.name || "Unknown worker",
    employeeId: person?.employee_id || null,
    shiftId: person?.shift_id || null,
    latestCheckIn: null,
    latestCheckOut: null,
  };
}

export function buildAttendanceSessionState({
  persons = [],
  attendanceRecords = [],
  gateReviews = [],
}) {
  const personsById = new Map(persons.map((person) => [person.id, person]));
  const approvedReviews = gateReviews
    .filter((review) => review.status === "APPROVED")
    .sort(
      (left, right) =>
        toTimestamp(left.decided_at || left.timestamp) -
        toTimestamp(right.decided_at || right.timestamp),
    );
  const usedReviewIds = new Set();

  const grantedRecords = attendanceRecords
    .filter((record) => record.access_granted)
    .sort((left, right) => toTimestamp(left.timestamp) - toTimestamp(right.timestamp))
    .map((record) => {
      const matchedReview = findMatchingApprovedReview(
        record,
        approvedReviews,
        usedReviewIds,
      );

      return {
        ...record,
        manualOverrideReview: matchedReview,
        manualOverride: usesManualOverride(record, matchedReview),
      };
    });

  const activeSessionsByPerson = new Map();
  const completedSessions = [];

  grantedRecords.forEach((record) => {
    const sessionKey = record.person_id || `person-name:${record.person_name}`;
    const currentSession = activeSessionsByPerson.get(sessionKey) || null;

    if (record.direction === "ENTRY") {
      const nextSession = createSessionShell(record, personsById);
      nextSession.checkIn = record;
      if (record.manualOverride) {
        nextSession.hasManualOverride = true;
        nextSession.manualOverrideDirections.push("Check-In");
        nextSession.manualOverrideDetails.push(
          buildManualOverrideDetail(
            record,
            record.manualOverrideReview,
            "Check-In",
          ),
        );
      }
      nextSession.ppeDetails.checkIn = normalizePpeDetails(record.ppe_details);
      activeSessionsByPerson.set(sessionKey, nextSession);
      return;
    }

    if (!currentSession) {
      return;
    }

    currentSession.checkOut = record;
    if (record.manualOverride) {
      currentSession.hasManualOverride = true;
      currentSession.manualOverrideDirections.push("Check-Out");
      currentSession.manualOverrideDetails.push(
        buildManualOverrideDetail(
          record,
          record.manualOverrideReview,
          "Check-Out",
        ),
      );
    }
    currentSession.ppeDetails.checkOut = normalizePpeDetails(record.ppe_details);
    completedSessions.push(currentSession);
    activeSessionsByPerson.delete(sessionKey);
  });

  const activeSessions = [...activeSessionsByPerson.values()].sort(
    (left, right) =>
      toTimestamp(right.checkIn?.timestamp) - toTimestamp(left.checkIn?.timestamp),
  );
  const sortedCompletedSessions = [...completedSessions].sort(
    (left, right) =>
      toTimestamp(right.checkOut?.timestamp || right.checkIn?.timestamp) -
      toTimestamp(left.checkOut?.timestamp || left.checkIn?.timestamp),
  );
  const rosterCardsByPerson = new Map();

  persons
    .filter((person) => person.is_active !== false)
    .forEach((person) => {
      rosterCardsByPerson.set(
        person.id || `person-name:${person.name || "unknown"}`,
        createEmptyRosterCard(person),
      );
    });

  activeSessions.forEach((session) => {
    const rosterKey = session.personId || `person-name:${session.personName || session.id}`;
    const existingCard =
      rosterCardsByPerson.get(rosterKey) ||
      {
        id: rosterKey,
        personId: session.personId || null,
        personName: session.personName || "Unknown worker",
        employeeId: session.employeeId || null,
        shiftId: session.shiftId || null,
        latestCheckIn: null,
        latestCheckOut: null,
      };

    existingCard.personId = session.personId || existingCard.personId;
    existingCard.personName = session.personName || existingCard.personName;
    existingCard.employeeId = session.employeeId || existingCard.employeeId;
    existingCard.shiftId = session.shiftId || existingCard.shiftId;
    existingCard.latestCheckIn = session.checkIn
      ? buildRosterEvent(
          session.checkIn,
          personsById,
          session.checkIn.manualOverrideReview,
        )
      : null;
    existingCard.latestCheckOut = null;

    rosterCardsByPerson.set(rosterKey, existingCard);
  });

  const rosterCards = [...rosterCardsByPerson.values()].sort((left, right) => {
    const leftIsActive = Boolean(left.latestCheckIn);
    const rightIsActive = Boolean(right.latestCheckIn);

    if (leftIsActive !== rightIsActive) {
      return rightIsActive ? 1 : -1;
    }

    if (leftIsActive && rightIsActive) {
      return (
        toTimestamp(right.latestCheckIn?.timestamp) -
        toTimestamp(left.latestCheckIn?.timestamp)
      );
    }

    return left.personName.localeCompare(right.personName);
  });

  return {
    activeSessions,
    completedSessions: sortedCompletedSessions,
    rosterCards,
  };
}
