import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useSearchParams } from "react-router-dom";
import {
  deletePerson,
  enrollPersonWithMedia,
  getPersons,
  getRecognizerStatus,
  updatePerson,
  updatePersonEnrollmentMedia,
} from "../services/api";
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  UsersIcon,
  VideoIcon,
} from "../components/icons";
import {
  readTestDatabase,
  TEST_DATABASE_UPDATED_EVENT,
} from "../utils/testDatabase";

const SHIFT_OPTIONS = [
  { id: "day", label: "Day Shift" },
  { id: "swing", label: "Swing Shift" },
  { id: "night", label: "Night Shift" },
];

function getShiftLabel(shiftId) {
  return SHIFT_OPTIONS.find((shift) => shift.id === shiftId)?.label || "All Shifts";
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

function Enrollment() {
  const [searchParams] = useSearchParams();
  const [persons, setPersons] = useState([]);
  const [recognizerStatus, setRecognizerStatus] = useState(null);
  const [savedWorkers, setSavedWorkers] = useState(
    () => readTestDatabase().attendanceWorkers,
  );
  const [selectedWorkerId, setSelectedWorkerId] = useState("");
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [editingPersonId, setEditingPersonId] = useState(null);
  const [editForm, setEditForm] = useState({
    name: "",
    employeeId: "",
    shiftId: "day",
    mergeMode: "append",
  });
  const [editFiles, setEditFiles] = useState([]);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const editFileInputRef = useRef(null);
  const requestedWorkerIdRef = useRef("");

  const selectedImages = useMemo(
    () => selectedFiles.filter((file) => file.type.startsWith("image/")),
    [selectedFiles],
  );
  const selectedVideos = useMemo(
    () => selectedFiles.filter((file) => file.type.startsWith("video/")),
    [selectedFiles],
  );
  const selectedEditImages = useMemo(
    () => editFiles.filter((file) => file.type.startsWith("image/")),
    [editFiles],
  );
  const selectedEditVideos = useMemo(
    () => editFiles.filter((file) => file.type.startsWith("video/")),
    [editFiles],
  );
  const selectedWorker = useMemo(
    () =>
      savedWorkers.find((worker) => worker.id === selectedWorkerId) || null,
    [savedWorkers, selectedWorkerId],
  );
  const matchedEnrolledPerson = useMemo(() => {
    if (!selectedWorker) {
      return null;
    }

    const normalizedWorkerBadge = selectedWorker.badgeId?.trim().toLowerCase();
    const normalizedWorkerName = selectedWorker.name?.trim().toLowerCase();

    return (
      persons.find((person) => {
        const normalizedEmployeeId = person.employee_id?.trim().toLowerCase();
        const normalizedPersonName = person.name?.trim().toLowerCase();

        return (
          (normalizedWorkerBadge && normalizedEmployeeId === normalizedWorkerBadge) ||
          (normalizedWorkerName && normalizedPersonName === normalizedWorkerName)
        );
      }) || null
    );
  }, [persons, selectedWorker]);
  const requestedWorkerId = searchParams.get("workerId") || "";

  const loadData = async () => {
    try {
      const [personList, status] = await Promise.all([
        getPersons(),
        getRecognizerStatus(),
      ]);
      setPersons(personList || []);
      setRecognizerStatus(status);
    } catch (loadError) {
      setError(loadError.message || "Failed to load enrollment data.");
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    const syncSavedWorkers = () => {
      setSavedWorkers(readTestDatabase().attendanceWorkers);
    };

    syncSavedWorkers();
    window.addEventListener(TEST_DATABASE_UPDATED_EVENT, syncSavedWorkers);

    return () => {
      window.removeEventListener(TEST_DATABASE_UPDATED_EVENT, syncSavedWorkers);
    };
  }, []);

  useEffect(() => {
    requestedWorkerIdRef.current = "";
  }, [requestedWorkerId]);

  useEffect(() => {
    if (!requestedWorkerId || requestedWorkerIdRef.current === requestedWorkerId) {
      return;
    }

    const requestedWorker = savedWorkers.find(
      (worker) => worker.id === requestedWorkerId,
    );
    if (!requestedWorker) {
      return;
    }

    requestedWorkerIdRef.current = requestedWorkerId;
    setSelectedWorkerId(requestedWorker.id);
    setError("");
  }, [requestedWorkerId, savedWorkers]);

  useEffect(() => {
    if (
      selectedWorkerId &&
      !savedWorkers.some((worker) => worker.id === selectedWorkerId)
    ) {
      setSelectedWorkerId("");
    }
  }, [savedWorkers, selectedWorkerId]);

  const handleSavedWorkerSelect = (event) => {
    const nextWorkerId = event.target.value;
    setSelectedWorkerId(nextWorkerId);
    setError("");
  };

  const handleMediaUpload = (event) => {
    const files = Array.from(event.target.files || []);
    setSelectedFiles(files);
  };

  const resetEditState = () => {
    setEditingPersonId(null);
    setEditForm({
      name: "",
      employeeId: "",
      shiftId: "day",
      mergeMode: "append",
    });
    setEditFiles([]);
    if (editFileInputRef.current) {
      editFileInputRef.current.value = "";
    }
  };

  const handleEditMediaUpload = (event) => {
    const files = Array.from(event.target.files || []);
    setEditFiles(files);
  };

  const handleStartEditing = (person) => {
    setError("");
    setEditingPersonId(person.id);
    setEditForm({
      name: person.name,
      employeeId: person.employee_id || "",
      shiftId: person.shift_id || "day",
      mergeMode: "append",
    });
    setEditFiles([]);
    if (editFileInputRef.current) {
      editFileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!selectedWorker) {
      setError("Select a saved worker from Settings before enrolling.");
      return;
    }

    if (matchedEnrolledPerson) {
      setError("This worker is already enrolled. Use Edit Enrollment below to add more media.");
      return;
    }

    if (selectedFiles.length === 0) {
      setError("Add multiple photos or a short video before enrolling.");
      return;
    }

    setIsSaving(true);
    setError("");
    try {
      await enrollPersonWithMedia({
        name: selectedWorker.name.trim(),
        employeeId: selectedWorker.badgeId.trim(),
        shiftId: mapWorkerShiftToEnrollmentShift(selectedWorker.shift),
        files: selectedFiles,
      });
      setSelectedFiles([]);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await loadData();
    } catch (saveError) {
      setError(saveError.message || "Failed to enroll worker.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (personId) => {
    try {
      setError("");
      await deletePerson(personId);
      if (editingPersonId === personId) {
        resetEditState();
      }
      await loadData();
    } catch (deleteError) {
      setError(deleteError.message || "Failed to remove enrolled worker.");
    }
  };

  const handleUpdate = async (event) => {
    event.preventDefault();
    if (!editingPersonId) {
      return;
    }

    if (!editForm.name.trim()) {
      setError("Worker name is required.");
      return;
    }

    setIsUpdating(true);
    setError("");
    try {
      if (editFiles.length > 0) {
        await updatePersonEnrollmentMedia({
          personId: editingPersonId,
          name: editForm.name.trim(),
          employeeId: editForm.employeeId.trim(),
          shiftId: editForm.shiftId,
          mergeMode: editForm.mergeMode,
          files: editFiles,
        });
      } else {
        await updatePerson(editingPersonId, {
          name: editForm.name.trim(),
          employee_id: editForm.employeeId.trim() || null,
          shift_id: editForm.shiftId,
          is_active: true,
        });
      }

      await loadData();
      resetEditState();
    } catch (updateError) {
      setError(updateError.message || "Failed to update worker profile.");
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="min-h-screen p-6 xl:p-8">
      <motion.section
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <p className="eyebrow mb-2">Gate Identity Setup</p>
        <h1 className="font-display text-3xl font-bold text-primary md:text-4xl">
          Worker Enrollment
        </h1>
        <p className="mt-3 max-w-3xl text-sm text-secondary">
          Use either 6 to 12 face photos from different angles or one 5 to 10 second
          video where the worker slowly turns left and right. The backend now keeps a
          compact multi-view embedding set for faster matching.
        </p>
      </motion.section>

      {error ? (
        <div className="mb-6 rounded-2xl border border-[var(--color-error)] bg-[var(--color-error-muted)] px-5 py-4">
          <p className="text-sm font-semibold" style={{ color: "var(--color-error)" }}>
            {error}
          </p>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1fr_1.15fr]">
        <section className="panel">
          <div className="panel__header">
            <div>
              <p className="eyebrow text-[10px]">Recognizer</p>
              <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                Runtime Status
              </h2>
            </div>
          </div>
          <div className="panel__content space-y-4">
            <div className="rounded-2xl border border-default bg-surface px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-base font-semibold text-primary">
                    {recognizerStatus?.available
                      ? "ArcFace embeddings active"
                      : "Enrollment storage active"}
                  </p>
                  <p className="mt-2 text-sm text-secondary">
                    {recognizerStatus?.message ||
                      "Loading recognition runtime status."}
                  </p>
                </div>
                <span
                  className={
                    recognizerStatus?.available
                      ? "badge badge-success"
                      : "badge badge-warning"
                  }
                >
                  {recognizerStatus?.available ? "Ready" : "Pending"}
                </span>
              </div>
            </div>

            <form
              onSubmit={handleSubmit}
              className="grid gap-3 rounded-2xl border border-default bg-surface p-4"
            >
              <div className="rounded-2xl border border-default bg-card p-4">
                <label className="block text-sm font-semibold text-primary">
                  Select saved worker
                </label>
                <p className="mt-1 text-sm text-secondary">
                  Pull the worker name and badge from Settings so you do not type them
                  again.
                </p>
                <select
                  value={selectedWorkerId}
                  onChange={handleSavedWorkerSelect}
                  className="input mt-3 h-12"
                >
                  <option value="">Choose from attendance workers</option>
                  {savedWorkers.map((worker) => (
                    <option key={worker.id} value={worker.id}>
                      {worker.name}
                      {worker.badgeId ? ` • ${worker.badgeId}` : ""}
                    </option>
                  ))}
                </select>
                {savedWorkers.length === 0 ? (
                  <p className="mt-3 text-sm text-secondary">
                    No attendance workers have been saved in Settings yet.
                  </p>
                ) : null}
                {selectedWorker ? (
                  <div className="mt-3 rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="badge badge-accent">
                        {selectedWorker.badgeId || "No badge ID"}
                      </span>
                      <span className="badge badge-info">
                        {selectedWorker.shift || "Shift pending"}
                      </span>
                      {matchedEnrolledPerson ? (
                        <span className="badge badge-success">
                          Already enrolled
                        </span>
                      ) : (
                        <span className="badge badge-warning">
                        Not enrolled yet
                      </span>
                    )}
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      <div className="rounded-xl border border-default bg-card px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-secondary">
                          Worker Name
                        </p>
                        <p className="mt-2 text-sm font-semibold text-primary">
                          {selectedWorker.name}
                        </p>
                      </div>
                      <div className="rounded-xl border border-default bg-card px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-secondary">
                          Badge ID
                        </p>
                        <p className="mt-2 text-sm font-semibold text-primary">
                          {selectedWorker.badgeId || "No badge ID"}
                        </p>
                      </div>
                      <div className="rounded-xl border border-default bg-card px-4 py-3">
                        <p className="text-xs uppercase tracking-[0.2em] text-secondary">
                          Shift
                        </p>
                        <p className="mt-2 text-sm font-semibold text-primary">
                          {selectedWorker.shift || "Shift pending"}
                        </p>
                      </div>
                    </div>
                    <p className="mt-3 text-sm text-secondary">
                      {matchedEnrolledPerson
                        ? "This worker already has an enrollment record below. Use Edit Enrollment if you want to add more media."
                        : "This enrollment will use the saved worker record exactly as shown above."}
                    </p>
                  </div>
                ) : null}
              </div>
              <div className="rounded-2xl border border-default bg-card p-4">
                <div className="flex flex-col gap-4">
                  <div className="flex items-start gap-4">
                    <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl border border-default bg-[var(--color-bg-surface)]">
                      {selectedVideos.length > 0 ? (
                        <VideoIcon size={28} className="text-accent" />
                      ) : (
                        <UsersIcon size={28} className="text-accent" />
                      )}
                    </div>
                    <div className="flex-1">
                      <label className="block text-sm font-semibold text-primary">
                        Enrollment media
                      </label>
                      <p className="mt-1 text-sm text-secondary">
                        Recommended: one short video or several images covering frontal
                        and side angles.
                      </p>
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm"
                        onChange={handleMediaUpload}
                        className="mt-3 block w-full text-sm text-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--color-accent-primary)] file:px-4 file:py-2 file:font-semibold file:text-white"
                      />
                    </div>
                  </div>

                  <div className="rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="badge badge-accent">
                        {selectedFiles.length} files selected
                      </span>
                      <span className="badge badge-info">
                        {selectedImages.length} images
                      </span>
                      <span className="badge badge-info">
                        {selectedVideos.length} videos
                      </span>
                    </div>
                    {selectedFiles.length > 0 ? (
                      <div className="mt-3 space-y-2">
                        {selectedFiles.slice(0, 6).map((file) => (
                          <p key={`${file.name}-${file.size}`} className="text-sm text-secondary">
                            {file.name}
                          </p>
                        ))}
                        {selectedFiles.length > 6 ? (
                          <p className="text-sm text-secondary">
                            +{selectedFiles.length - 6} more files
                          </p>
                        ) : null}
                      </div>
                    ) : (
                      <p className="mt-3 text-sm text-secondary">
                        No media selected yet.
                      </p>
                    )}
                  </div>
                </div>
              </div>
              <button
                type="submit"
                disabled={isSaving || !selectedWorker || Boolean(matchedEnrolledPerson)}
                className="btn btn-primary h-12 px-4"
              >
                {matchedEnrolledPerson
                  ? "Worker Already Enrolled"
                  : isSaving
                    ? "Processing..."
                    : "Enroll Worker"}
              </button>
            </form>
          </div>
        </section>

        <section className="panel">
          <div className="panel__header">
            <div>
              <p className="eyebrow text-[10px]">Registry</p>
              <h2 className="mt-1 font-display text-xl font-semibold text-primary">
                Enrolled Workers
              </h2>
            </div>
            <span className="badge badge-accent">{persons.length} workers</span>
          </div>
          <div className="panel__content space-y-4">
            {persons.length > 0 ? (
              persons.map((person) => (
                <article
                  key={person.id}
                  className="rounded-2xl border border-default bg-surface p-4"
                >
                  <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                    <div className="flex items-center gap-4">
                      <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl border border-default bg-card">
                        {person.thumbnail_data_url ? (
                          <img
                            src={person.thumbnail_data_url}
                            alt={person.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <UsersIcon size={22} className="text-accent" />
                        )}
                      </div>
                      <div>
                        <p className="text-lg font-semibold text-primary">{person.name}</p>
                        <p className="mt-1 text-sm text-secondary">
                          {person.employee_id || "No employee ID"}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <span className="badge badge-accent">
                            {getShiftLabel(person.shift_id)}
                          </span>
                          <span
                            className={
                              person.has_embedding
                                ? "badge badge-success"
                                : "badge badge-warning"
                            }
                          >
                            {person.has_embedding ? "Embedding ready" : "Pending ArcFace"}
                          </span>
                          <span className="badge badge-info">
                            {person.sample_count || 0} views kept
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          editingPersonId === person.id
                            ? resetEditState()
                            : handleStartEditing(person)
                        }
                        className="btn btn-secondary h-10 px-4"
                      >
                        {editingPersonId === person.id ? "Close Editor" : "Edit Enrollment"}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(person.id)}
                        className="btn h-10 px-4 text-white"
                        style={{ backgroundColor: "var(--color-error)" }}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 rounded-xl border border-default bg-card px-4 py-3">
                    <div className="flex items-start gap-3">
                      {person.has_embedding ? (
                        <CheckCircleIcon size={18} className="mt-0.5 text-[var(--color-success)]" />
                      ) : (
                        <AlertTriangleIcon size={18} className="mt-0.5 text-[var(--color-warning)]" />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm text-secondary">
                          {person.embedding_message ||
                            "No recognition metadata has been stored for this worker yet."}
                        </p>
                        {person.discarded_media?.length ? (
                          <p className="mt-2 text-xs text-secondary">
                            Skipped: {person.discarded_media.join(" | ")}
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  {editingPersonId === person.id ? (
                    <form
                      onSubmit={handleUpdate}
                      className="mt-4 grid gap-3 rounded-xl border border-default bg-card p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-primary">
                            Update worker profile
                          </p>
                          <p className="mt-1 text-sm text-secondary">
                            Append adds new angles to the existing face set. Replace
                            rebuilds the worker from only the fresh upload.
                          </p>
                        </div>
                        <span className="badge badge-info">
                          {person.sample_count || 0} current views
                        </span>
                      </div>

                      <input
                        type="text"
                        value={editForm.name}
                        onChange={(event) =>
                          setEditForm((current) => ({
                            ...current,
                            name: event.target.value,
                          }))
                        }
                        placeholder="Worker name"
                        className="input h-12"
                      />
                      <input
                        type="text"
                        value={editForm.employeeId}
                        onChange={(event) =>
                          setEditForm((current) => ({
                            ...current,
                            employeeId: event.target.value,
                          }))
                        }
                        placeholder="Badge or employee ID"
                        className="input h-12"
                      />
                      <div className="grid gap-3 md:grid-cols-2">
                        <select
                          value={editForm.shiftId}
                          onChange={(event) =>
                            setEditForm((current) => ({
                              ...current,
                              shiftId: event.target.value,
                            }))
                          }
                          className="input h-12"
                        >
                          {SHIFT_OPTIONS.map((shift) => (
                            <option key={shift.id} value={shift.id}>
                              {shift.label}
                            </option>
                          ))}
                        </select>
                        <select
                          value={editForm.mergeMode}
                          onChange={(event) =>
                            setEditForm((current) => ({
                              ...current,
                              mergeMode: event.target.value,
                            }))
                          }
                          className="input h-12"
                        >
                          <option value="append">Append New Media</option>
                          <option value="replace">Replace Face Set</option>
                        </select>
                      </div>

                      <div className="rounded-xl border border-default bg-[var(--color-bg-surface)] px-4 py-3">
                        <div className="flex items-start gap-4">
                          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl border border-default bg-card">
                            {selectedEditVideos.length > 0 ? (
                              <VideoIcon size={24} className="text-accent" />
                            ) : (
                              <UsersIcon size={24} className="text-accent" />
                            )}
                          </div>
                          <div className="flex-1">
                            <label className="block text-sm font-semibold text-primary">
                              New media
                            </label>
                            <p className="mt-1 text-sm text-secondary">
                              Leave this empty to save only the name, badge, or shift.
                            </p>
                            <input
                              ref={editFileInputRef}
                              type="file"
                              multiple
                              accept="image/png,image/jpeg,image/webp,video/mp4,video/quicktime,video/webm"
                              onChange={handleEditMediaUpload}
                              className="mt-3 block w-full text-sm text-secondary file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--color-accent-primary)] file:px-4 file:py-2 file:font-semibold file:text-white"
                            />
                          </div>
                        </div>

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          <span className="badge badge-accent">
                            {editFiles.length} files selected
                          </span>
                          <span className="badge badge-info">
                            {selectedEditImages.length} images
                          </span>
                          <span className="badge badge-info">
                            {selectedEditVideos.length} videos
                          </span>
                        </div>
                        {editFiles.length > 0 ? (
                          <div className="mt-3 space-y-2">
                            {editFiles.slice(0, 5).map((file) => (
                              <p key={`${file.name}-${file.size}`} className="text-sm text-secondary">
                                {file.name}
                              </p>
                            ))}
                            {editFiles.length > 5 ? (
                              <p className="text-sm text-secondary">
                                +{editFiles.length - 5} more files
                              </p>
                            ) : null}
                          </div>
                        ) : null}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <button
                          type="submit"
                          disabled={isUpdating}
                          className="btn btn-primary h-12 px-4"
                        >
                          {isUpdating ? "Saving..." : "Save Update"}
                        </button>
                        <button
                          type="button"
                          onClick={resetEditState}
                          className="btn btn-secondary h-12 px-4"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-default px-5 py-12 text-center">
                <UsersIcon size={30} className="mx-auto mb-3 text-accent" />
                <p className="text-base font-semibold text-primary">
                  No workers enrolled yet
                </p>
                <p className="mt-2 text-sm text-secondary">
                  Add the first worker with multi-view media so the gate attendance
                  module has a real identity registry.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default Enrollment;
