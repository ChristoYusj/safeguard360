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

export function parseBackendTimestamp(value) {
  if (!value) {
    return null;
  }

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === "number") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  if (typeof value !== "string") {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(trimmed);
  const normalized = hasTimezone
    ? trimmed
    : trimmed.includes("T")
      ? `${trimmed}Z`
      : `${trimmed.replace(" ", "T")}Z`;

  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
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

function hasTrackedPpeRequirements(ppeDetails) {
  return (normalizePpeDetails(ppeDetails).required_items || []).length > 0;
}

function hasRegisteredPpeViolation({ reviewReasons = [], ppeDetails }) {
  const normalizedPpeDetails = normalizePpeDetails(ppeDetails);
  const missingItems = normalizedPpeDetails.missing_items || [];

  if (!hasTrackedPpeRequirements(normalizedPpeDetails)) {
    return false;
  }

  return (
    normalizedPpeDetails.status === "non_compliant" ||
    normalizedPpeDetails.status === "uncertain" ||
    missingItems.length > 0 ||
    reviewReasons.includes("uncertain_ppe") ||
    reviewReasons.some((reason) => reason.startsWith("missing_")) ||
    normalizedPpeDetails.override_reason_type === "ppe_non_compliance" ||
    normalizedPpeDetails.override_reason_type === "combined"
  );
}

function buildPpeViolationSummary({ reviewReasons = [], ppeDetails, decisionNote = null }) {
  const normalizedPpeDetails = normalizePpeDetails(ppeDetails);
  const missingItems = normalizedPpeDetails.missing_items || [];

  if (missingItems.length > 0) {
    return `Missing ${missingItems.join(", ")}`;
  }
  if (reviewReasons.includes("uncertain_ppe")) {
    return "PPE status could not be confirmed automatically.";
  }
  if (normalizedPpeDetails.status === "non_compliant") {
    return "Required PPE was not detected.";
  }
  if (normalizedPpeDetails.status === "uncertain") {
    return "PPE needed operator confirmation.";
  }
  return decisionNote || "PPE violation recorded.";
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
  return parseBackendTimestamp(value)?.getTime() || 0;
}

export function getShiftIdForTimestamp(timestamp) {
  if (!timestamp) {
    return null;
  }

  const date = parseBackendTimestamp(timestamp);
  if (!date) {
    return null;
  }
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
  // If the worker has no explicit shift on file, leave the session shift-less
  // (null) so it stays visible regardless of which shift the operator has
  // selected. Falling back to a timestamp-derived shift would hide manual
  // approvals made outside the selected shift's hours, which in turn locks the
  // Check-Out button because onSiteCount stays at 0.
  const resolvedShiftId =
    person?.shift_id || (record.person_id ? null : getShiftIdForTimestamp(record.timestamp));

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
  const resolvedShiftId =
    person?.shift_id || (record.person_id ? null : getShiftIdForTimestamp(record.timestamp));

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
    snapshotDataUrl: record.snapshot_data_url || null,
  };
}

function buildRosterViolationFromReview(review, personsById) {
  if (!review?.person_id) {
    return null;
  }

  const reviewReasons = normalizeReviewReasons(review);
  const ppeDetails = normalizePpeDetails(review.ppe_details);
  if (!hasRegisteredPpeViolation({ reviewReasons, ppeDetails })) {
    return null;
  }

  const person = personsById.get(review.person_id) || null;
  const resolvedShiftId = person?.shift_id || null;
  const decision = review.status === "DENIED" ? "Entry denied" : "Override granted";

  return {
    id: `review:${review.id}`,
    personId: review.person_id,
    shiftId: resolvedShiftId,
    timestamp: review.decided_at || review.timestamp || null,
    decision,
    summary: buildPpeViolationSummary({
      reviewReasons,
      ppeDetails,
      decisionNote: review.decision_note || null,
    }),
    ppeDetails,
    reviewReasons,
    snapshotDataUrl: review.snapshot_data_url || null,
  };
}

function buildRosterViolationFromRecord(record, personsById, matchedReview = null) {
  if (!record?.person_id || record.direction !== "ENTRY") {
    return null;
  }

  if (matchedReview) {
    return buildRosterViolationFromReview(matchedReview, personsById);
  }

  const ppeDetails = normalizePpeDetails(record.ppe_details);
  if (
    record.ppe_compliant !== false ||
    !hasRegisteredPpeViolation({ reviewReasons: [], ppeDetails })
  ) {
    return null;
  }

  const person = personsById.get(record.person_id) || null;
  const resolvedShiftId = person?.shift_id || null;

  return {
    id: `attendance:${record.id}`,
    personId: record.person_id,
    shiftId: resolvedShiftId,
    timestamp: record.timestamp || null,
    decision: "Violation logged",
    summary: buildPpeViolationSummary({ ppeDetails }),
    ppeDetails,
    reviewReasons: [],
    snapshotDataUrl: record.snapshot_data_url || null,
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
  const rosterViolationIdsByPerson = new Map();

  const upsertRosterCard = (rosterKey, fallback = {}) => {
    const existingCard = rosterCardsByPerson.get(rosterKey);
    if (existingCard) {
      return existingCard;
    }

    const nextCard = {
      id: rosterKey,
      personId: fallback.personId || null,
      personName: fallback.personName || "Unknown worker",
      employeeId: fallback.employeeId || null,
      shiftId: fallback.shiftId || null,
      latestCheckIn: null,
      latestCheckOut: null,
      registeredViolations: [],
    };
    rosterCardsByPerson.set(rosterKey, nextCard);
    return nextCard;
  };

  const appendRosterViolation = (rosterKey, violation, fallback = {}) => {
    if (!violation) {
      return;
    }
    if (!rosterCardsByPerson.has(rosterKey)) {
      return;
    }

    const existingIds = rosterViolationIdsByPerson.get(rosterKey) || new Set();
    if (existingIds.has(violation.id)) {
      return;
    }

    existingIds.add(violation.id);
    rosterViolationIdsByPerson.set(rosterKey, existingIds);
    const card = upsertRosterCard(rosterKey, fallback);
    card.registeredViolations = [...card.registeredViolations, violation];
  };

  activeSessions.forEach((session) => {
    const rosterKey = session.personId || `person-name:${session.personName || session.id}`;
    const existingCard = upsertRosterCard(rosterKey, {
      personId: session.personId || null,
      personName: session.personName || "Unknown worker",
      employeeId: session.employeeId || null,
      shiftId: session.shiftId || null,
    });

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

  grantedRecords.forEach((record) => {
    const rosterKey = record.person_id || `person-name:${record.person_name || record.id}`;
    appendRosterViolation(
      rosterKey,
      buildRosterViolationFromRecord(record, personsById, record.manualOverrideReview),
      {
        personId: record.person_id || null,
        personName: record.person_name || "Unknown worker",
        employeeId: record.person_employee_id || null,
        shiftId:
          personsById.get(record.person_id)?.shift_id ||
          (record.person_id ? null : getShiftIdForTimestamp(record.timestamp)),
      },
    );
  });

  gateReviews
    .filter((review) => review.status !== "PENDING")
    .forEach((review) => {
      if (review.status === "APPROVED" && usedReviewIds.has(review.id)) {
        return;
      }

      const rosterKey = review.person_id || `person-name:${review.person_name || review.id}`;
      appendRosterViolation(
        rosterKey,
        buildRosterViolationFromReview(review, personsById),
        {
          personId: review.person_id || null,
          personName: review.person_name || "Unknown worker",
          employeeId: review.person_employee_id || null,
          shiftId:
            personsById.get(review.person_id)?.shift_id ||
            (review.person_id
              ? null
              : getShiftIdForTimestamp(review.decided_at || review.timestamp)),
        },
      );
    });

  rosterCardsByPerson.forEach((card) => {
    card.registeredViolations.sort(
      (leftViolation, rightViolation) =>
        toTimestamp(rightViolation.timestamp) - toTimestamp(leftViolation.timestamp),
    );
  });

  const rosterCards = [...rosterCardsByPerson.values()].sort(
    (left, right) =>
      toTimestamp(right.latestCheckIn?.timestamp) -
        toTimestamp(left.latestCheckIn?.timestamp) ||
      left.personName.localeCompare(right.personName),
  );

  return {
    activeSessions,
    completedSessions: sortedCompletedSessions,
    rosterCards,
  };
}
