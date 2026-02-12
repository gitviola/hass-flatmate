class HassFlatmateCleaningCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
    this._errorMessage = "";
    this._pendingDoneWeeks = new Set();
    this._pendingSwapWeeks = new Set();
    this._optimisticWeekPatches = new Map();
    this._modalOpen = false;
    this._modalWeekStart = "";
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = "";
    this._modalCleanerMemberId = "";
    this._swapModalOpen = false;
    this._swapModalWeekStart = "";
    this._swapModalAction = "swap";
    this._swapOriginalAssigneeMemberId = "";
    this._swapTargetMemberId = "";
  }

  static async getConfigElement() {
    return document.createElement("hass-flatmate-cleaning-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hass_flatmate_cleaning_schedule",
      title: "Cleaning Rotation",
      weeks: 5,
      layout: "interactive",
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Cleaning Rotation",
      weeks: 5,
      layout: "interactive",
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return this._isCompact() ? 5 : 8;
  }

  set hass(hass) {
    const nextSnapshot = this._buildStateSnapshot(hass);
    this._hass = hass;
    if (!this._config) {
      return;
    }
    if (nextSnapshot !== this._stateSnapshot) {
      this._stateSnapshot = nextSnapshot;
      this._render();
    }
  }

  _buildStateSnapshot(hass) {
    if (!hass || !this._config?.entity) {
      return "";
    }
    const stateObj = hass.states[this._config.entity];
    if (!stateObj) {
      return "missing";
    }
    const attrs = stateObj.attributes || {};
    return JSON.stringify({
      state: stateObj.state,
      weeks: attrs.weeks || [],
      members: attrs.members || [],
      service_domain: attrs.service_domain || "",
      service_mark_done: attrs.service_mark_done || "",
      service_mark_undone: attrs.service_mark_undone || "",
      service_mark_takeover_done: attrs.service_mark_takeover_done || "",
      service_swap_week: attrs.service_swap_week || "",
      layout: this._layout(),
      modal_open: this._modalOpen,
      modal_week_start: this._modalWeekStart,
      modal_choice: this._modalChoice,
      modal_assignee_member_id: this._modalAssigneeMemberId,
      modal_cleaner_member_id: this._modalCleanerMemberId,
      swap_modal_open: this._swapModalOpen,
      swap_modal_week_start: this._swapModalWeekStart,
      swap_modal_action: this._swapModalAction,
      swap_original_assignee_member_id: this._swapOriginalAssigneeMemberId,
      swap_target_member_id: this._swapTargetMemberId,
      pending_done: [...this._pendingDoneWeeks],
      pending_swap: [...this._pendingSwapWeeks],
      optimistic_patches: [...this._optimisticWeekPatches.entries()],
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _serviceMeta(attributes) {
    return {
      domain: attributes.service_domain || "hass_flatmate",
      markDone: attributes.service_mark_done || "hass_flatmate_mark_cleaning_done",
      markUndone: attributes.service_mark_undone || "hass_flatmate_mark_cleaning_undone",
      markTakeoverDone:
        attributes.service_mark_takeover_done || "hass_flatmate_mark_cleaning_takeover_done",
      swapWeek: attributes.service_swap_week || "hass_flatmate_swap_cleaning_week",
    };
  }

  _layout() {
    const value = String(this._config?.layout || "interactive").toLowerCase();
    return value === "compact" ? "compact" : "interactive";
  }

  _isCompact() {
    return this._layout() === "compact";
  }

  _memberMap(members) {
    const map = new Map();
    for (const member of members) {
      const id = Number(member?.member_id);
      const name = String(member?.name || "").trim();
      if (Number.isInteger(id) && id > 0 && name) {
        map.set(id, name);
      }
    }
    return map;
  }

  _memberName(memberMap, memberId) {
    if (!Number.isInteger(memberId) || memberId <= 0) {
      return "Unknown";
    }
    return memberMap.get(memberId) || `Member ${memberId}`;
  }

  _currentMemberId(members) {
    const userId = String(this._hass?.user?.id || "");
    if (!userId) {
      return null;
    }
    for (const member of members) {
      const memberId = Number(member?.member_id);
      const memberUserId = member?.ha_user_id ? String(member.ha_user_id) : "";
      if (Number.isInteger(memberId) && memberId > 0 && memberUserId && memberUserId === userId) {
        return memberId;
      }
    }
    return null;
  }

  _rowDateRange(row) {
    const start = row?.week_start ? new Date(row.week_start) : null;
    const end = row?.week_end ? new Date(row.week_end) : null;
    if (!start || Number.isNaN(start.getTime()) || !end || Number.isNaN(end.getTime())) {
      return "Unknown dates";
    }

    const dateFmt = new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    });
    return `${dateFmt.format(start)} - ${dateFmt.format(end)}`;
  }

  _weekTitle(row, index) {
    if (row?.is_previous) {
      return "Previous week";
    }
    if (row?.is_current) {
      return "This week";
    }
    if (row?.is_next || index === 1) {
      return "Next week";
    }
    if (row?.week_number != null) {
      return `W${row.week_number}`;
    }
    return "Upcoming";
  }

  _coerceWeeks(value) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isInteger(parsed)) {
      return 5;
    }
    return Math.max(3, Math.min(parsed, 12));
  }

  _resolveModalWeek(weeks) {
    if (!this._modalWeekStart) {
      return null;
    }
    return weeks.find((row) => row.week_start === this._modalWeekStart) || null;
  }

  _resolveSwapModalWeek(weeks) {
    if (!this._swapModalWeekStart) {
      return null;
    }
    return weeks.find((row) => row.week_start === this._swapModalWeekStart) || null;
  }

  _parseWeekDate(value) {
    if (!value) {
      return null;
    }
    const parsed = new Date(`${value}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return parsed;
  }

  _normalizePatchValue(value) {
    return value == null ? null : value;
  }

  _setWeekPatch(weekStart, patch) {
    if (!weekStart || !patch || typeof patch !== "object") {
      return;
    }
    const nextPatch = {};
    for (const [key, value] of Object.entries(patch)) {
      nextPatch[key] = this._normalizePatchValue(value);
    }
    this._optimisticWeekPatches.set(String(weekStart), nextPatch);
  }

  _clearWeekPatch(weekStart) {
    if (!weekStart) {
      return;
    }
    this._optimisticWeekPatches.delete(String(weekStart));
  }

  _findCompensationPreviewWeek(weeks, cleanerMemberId, sourceWeekStart) {
    if (!Number.isInteger(cleanerMemberId) || cleanerMemberId <= 0 || !sourceWeekStart) {
      return null;
    }

    const sourceDate = this._parseWeekDate(sourceWeekStart);
    if (!sourceDate) {
      return null;
    }

    const sortedWeeks = weeks
      .slice()
      .sort((a, b) => String(a?.week_start || "").localeCompare(String(b?.week_start || "")));

    for (const row of sortedWeeks) {
      const rowDate = this._parseWeekDate(row?.week_start);
      if (!rowDate || rowDate <= sourceDate) {
        continue;
      }

      const baselineId = Number(
        row?.original_assignee_member_id ?? row?.baseline_assignee_member_id ?? row?.assignee_member_id
      );
      if (!Number.isInteger(baselineId) || baselineId !== cleanerMemberId) {
        continue;
      }

      if (row?.override_type) {
        continue;
      }

      return row;
    }

    return null;
  }

  _closeDoneModal() {
    this._modalOpen = false;
    this._modalWeekStart = "";
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = "";
    this._modalCleanerMemberId = "";
    this._render();
  }

  _closeSwapModal() {
    this._swapModalOpen = false;
    this._swapModalWeekStart = "";
    this._swapModalAction = "swap";
    this._swapOriginalAssigneeMemberId = "";
    this._swapTargetMemberId = "";
    this._render();
  }

  _openDoneModal(weekRow, members) {
    if (!weekRow || !weekRow.week_start) {
      return;
    }
    const assigneeMemberId = Number(weekRow.assignee_member_id);
    if (!Number.isInteger(assigneeMemberId) || assigneeMemberId <= 0) {
      return;
    }
    const actorMemberId = this._currentMemberId(members);
    const fallbackCleaner = members
      .map((member) => Number(member?.member_id))
      .find((memberId) => Number.isInteger(memberId) && memberId > 0 && memberId !== assigneeMemberId);

    const defaultCleaner =
      Number.isInteger(actorMemberId) && actorMemberId > 0 && actorMemberId !== assigneeMemberId
        ? actorMemberId
        : fallbackCleaner;

    this._modalOpen = true;
    this._swapModalOpen = false;
    this._modalWeekStart = weekRow.week_start;
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = String(assigneeMemberId);
    this._modalCleanerMemberId = defaultCleaner ? String(defaultCleaner) : "";
    this._errorMessage = "";
    this._render();
  }

  _openSwapModal(weekRow, members) {
    if (!weekRow || !weekRow.week_start) {
      return;
    }

    const originalAssigneeId = Number(weekRow.original_assignee_member_id || weekRow.assignee_member_id);
    if (!Number.isInteger(originalAssigneeId) || originalAssigneeId <= 0) {
      return;
    }

    const availableTargets = members
      .map((member) => Number(member?.member_id))
      .filter((memberId) => Number.isInteger(memberId) && memberId > 0 && memberId !== originalAssigneeId);

    if (availableTargets.length === 0) {
      this._errorMessage = "No other active flatmate is available for a swap.";
      this._render();
      return;
    }

    const actorMemberId = this._currentMemberId(members);
    const currentEffectiveId = Number(weekRow.assignee_member_id);
    const defaultTarget =
      weekRow.override_type === "manual_swap" &&
      Number.isInteger(currentEffectiveId) &&
      currentEffectiveId > 0 &&
      currentEffectiveId !== originalAssigneeId
        ? currentEffectiveId
        : Number.isInteger(actorMemberId) &&
            actorMemberId > 0 &&
            actorMemberId !== originalAssigneeId
          ? actorMemberId
          : availableTargets[0];

    this._swapModalOpen = true;
    this._modalOpen = false;
    this._swapModalWeekStart = String(weekRow.week_start);
    this._swapModalAction = "swap";
    this._swapOriginalAssigneeMemberId = String(originalAssigneeId);
    this._swapTargetMemberId = String(defaultTarget);
    this._errorMessage = "";
    this._render();
  }

  _isNonAssignee(row, members) {
    const assigneeMemberId = Number(row?.assignee_member_id);
    if (!Number.isInteger(assigneeMemberId) || assigneeMemberId <= 0) {
      return false;
    }

    const currentMemberId = this._currentMemberId(members);
    if (Number.isInteger(currentMemberId) && currentMemberId > 0) {
      return currentMemberId !== assigneeMemberId;
    }

    const currentUserId = String(this._hass?.user?.id || "");
    const assigneeUserId = row?.assignee_user_id ? String(row.assignee_user_id) : "";
    if (currentUserId && assigneeUserId) {
      return currentUserId !== assigneeUserId;
    }

    return false;
  }

  async _callService(service, data) {
    if (!this._hass || !this._stateObj) {
      return;
    }
    const meta = this._serviceMeta(this._stateObj.attributes || {});
    await this._hass.callService(meta.domain, service, data);
  }

  async _requestEntityRefresh() {
    if (!this._hass || !this._config?.entity) {
      return;
    }
    try {
      await this._hass.callService("homeassistant", "update_entity", {
        entity_id: this._config.entity,
      });
    } catch (_error) {}
  }

  async _runWeekAction(
    weekStart,
    action,
    fallbackError,
    { optimisticPatch = null, rollbackPatch = null } = {}
  ) {
    if (!weekStart || this._pendingDoneWeeks.has(weekStart)) {
      return false;
    }

    this._pendingDoneWeeks.add(weekStart);
    if (optimisticPatch) {
      this._setWeekPatch(weekStart, optimisticPatch);
    }
    this._errorMessage = "";
    this._render();

    let ok = false;
    try {
      await action();
      this._requestEntityRefresh();
      ok = true;
    } catch (error) {
      if (rollbackPatch) {
        this._setWeekPatch(weekStart, rollbackPatch);
      } else {
        this._clearWeekPatch(weekStart);
      }
      this._errorMessage = error?.message || fallbackError;
      this._render();
    } finally {
      this._pendingDoneWeeks.delete(weekStart);
      this._render();
    }

    return ok;
  }

  async _markDone(row, completedByMemberId = null) {
    const weekStart = String(row?.week_start || "");
    if (!weekStart) {
      return false;
    }
    const assigneeMemberId = Number(row?.assignee_member_id);
    const completedById =
      Number.isInteger(completedByMemberId) && completedByMemberId > 0
        ? completedByMemberId
        : Number.isInteger(assigneeMemberId) && assigneeMemberId > 0
          ? assigneeMemberId
          : null;
    const payload = completedByMemberId
      ? { week_start: weekStart, completed_by_member_id: completedByMemberId }
      : { week_start: weekStart };
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    return this._runWeekAction(
      weekStart,
      async () => {
        await this._callService(meta.markDone, payload);
      },
      "Unable to mark cleaning as done",
      {
        optimisticPatch: {
          status: "done",
          completion_mode: "own",
          completed_by_member_id: completedById,
        },
        rollbackPatch: {
          status: row?.status || "pending",
          completion_mode: row?.completion_mode || null,
          completed_by_member_id: row?.completed_by_member_id || null,
        },
      }
    );
  }

  async _markUndone(row) {
    const weekStart = String(row?.week_start || "");
    if (!weekStart) {
      return false;
    }
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    return this._runWeekAction(
      weekStart,
      async () => {
        await this._callService(meta.markUndone, { week_start: weekStart });
      },
      "Unable to mark cleaning as undone",
      {
        optimisticPatch: {
          status: "pending",
          completion_mode: null,
          completed_by_member_id: null,
        },
        rollbackPatch: {
          status: row?.status || "done",
          completion_mode: row?.completion_mode || null,
          completed_by_member_id: row?.completed_by_member_id || null,
        },
      }
    );
  }

  async _markTakeoverDone(row, originalAssigneeMemberId, cleanerMemberId) {
    const weekStart = String(row?.week_start || "");
    if (!weekStart) {
      return false;
    }
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    return this._runWeekAction(
      weekStart,
      async () => {
        await this._callService(meta.markTakeoverDone, {
          week_start: weekStart,
          original_assignee_member_id: originalAssigneeMemberId,
          cleaner_member_id: cleanerMemberId,
        });
      },
      "Unable to record takeover completion",
      {
        optimisticPatch: {
          status: "done",
          completion_mode: "takeover",
          completed_by_member_id: cleanerMemberId,
        },
        rollbackPatch: {
          status: row?.status || "pending",
          completion_mode: row?.completion_mode || null,
          completed_by_member_id: row?.completed_by_member_id || null,
        },
      }
    );
  }

  async _runSwapAction(
    weekStart,
    action,
    fallbackError,
    { optimisticPatch = null, rollbackPatch = null } = {}
  ) {
    if (!weekStart || this._pendingSwapWeeks.has(weekStart)) {
      return false;
    }

    this._pendingSwapWeeks.add(weekStart);
    if (optimisticPatch) {
      this._setWeekPatch(weekStart, optimisticPatch);
    }
    this._errorMessage = "";
    this._render();

    let ok = false;
    try {
      await action();
      this._requestEntityRefresh();
      ok = true;
    } catch (error) {
      if (rollbackPatch) {
        this._setWeekPatch(weekStart, rollbackPatch);
      } else {
        this._clearWeekPatch(weekStart);
      }
      this._errorMessage = error?.message || fallbackError;
      this._render();
    } finally {
      this._pendingSwapWeeks.delete(weekStart);
      this._render();
    }

    return ok;
  }

  async _swapWeek(row, memberAId, memberBId, cancel = false) {
    const weekStart = String(row?.week_start || "");
    if (!weekStart) {
      return false;
    }
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    const memberMap = this._memberMap(Array.isArray(this._stateObj?.attributes?.members) ? this._stateObj.attributes.members : []);
    const rollbackEffectiveId = row?.assignee_member_id ?? null;
    const rollbackOverrideType = row?.override_type || null;
    const rollbackName =
      Number.isInteger(Number(rollbackEffectiveId)) && Number(rollbackEffectiveId) > 0
        ? this._memberName(memberMap, Number(rollbackEffectiveId))
        : row?.assignee_name || null;
    const optimisticEffectiveId = cancel ? memberAId : memberBId;
    return this._runSwapAction(
      weekStart,
      async () => {
        await this._callService(meta.swapWeek, {
          week_start: weekStart,
          member_a_id: memberAId,
          member_b_id: memberBId,
          cancel,
        });
      },
      cancel ? "Unable to cancel swap" : "Unable to apply swap",
      {
        optimisticPatch: {
          override_type: cancel ? null : "manual_swap",
          assignee_member_id: optimisticEffectiveId,
          assignee_name: this._memberName(memberMap, optimisticEffectiveId),
        },
        rollbackPatch: {
          override_type: rollbackOverrideType,
          assignee_member_id: rollbackEffectiveId,
          assignee_name: rollbackName,
        },
      }
    );
  }

  async _toggleDone(row, members) {
    if (!row || !row.week_start) {
      return;
    }
    const weekStart = String(row.week_start);
    const status = String(row.status || "pending");
    if (status === "done") {
      await this._markUndone(row);
      return;
    }

    if (this._isNonAssignee(row, members)) {
      this._openDoneModal(row, members);
      return;
    }

    await this._markDone(row);
  }

  async _submitDoneModal(weeks, members) {
    const row = this._resolveModalWeek(weeks);
    if (!row || !row.week_start) {
      this._closeDoneModal();
      return;
    }

    const assigneeMemberId = Number(this._modalAssigneeMemberId || row.assignee_member_id);
    if (!Number.isInteger(assigneeMemberId) || assigneeMemberId <= 0) {
      this._errorMessage = "Cannot resolve assignee for this week.";
      this._render();
      return;
    }

    let ok = false;
    if (this._modalChoice === "takeover") {
      const cleanerMemberId = Number(this._modalCleanerMemberId);
      if (!Number.isInteger(cleanerMemberId) || cleanerMemberId <= 0) {
        this._errorMessage = "Select the flatmate who cleaned this shift.";
        this._render();
        return;
      }
      if (cleanerMemberId === assigneeMemberId) {
        this._errorMessage = "Cleaner must be different from the original assignee.";
        this._render();
        return;
      }
      ok = await this._markTakeoverDone(row, assigneeMemberId, cleanerMemberId);
    } else {
      ok = await this._markDone(row, assigneeMemberId);
    }

    if (ok) {
      this._closeDoneModal();
    }
  }

  async _submitSwapModal(weeks, _members) {
    const row = this._resolveSwapModalWeek(weeks);
    if (!row || !row.week_start) {
      this._closeSwapModal();
      return;
    }

    const originalAssigneeId = Number(
      this._swapOriginalAssigneeMemberId || row.original_assignee_member_id || row.assignee_member_id
    );
    if (!Number.isInteger(originalAssigneeId) || originalAssigneeId <= 0) {
      this._errorMessage = "Cannot resolve the original assignee for this week.";
      this._render();
      return;
    }

    const isCancel = this._swapModalAction === "cancel";
    let ok = false;

    if (isCancel) {
      if (row.override_type !== "manual_swap") {
        this._errorMessage = "No manual swap exists for this week.";
        this._render();
        return;
      }
      const swappedWithId = Number(row.assignee_member_id);
      if (
        !Number.isInteger(swappedWithId) ||
        swappedWithId <= 0 ||
        swappedWithId === originalAssigneeId
      ) {
        this._errorMessage = "Cannot resolve the existing swap participants.";
        this._render();
        return;
      }
      ok = await this._swapWeek(row, originalAssigneeId, swappedWithId, true);
    } else {
      const swapWithId = Number(this._swapTargetMemberId);
      if (!Number.isInteger(swapWithId) || swapWithId <= 0) {
        this._errorMessage = "Select a flatmate to swap with.";
        this._render();
        return;
      }
      if (swapWithId === originalAssigneeId) {
        this._errorMessage = "Swap requires two different flatmates.";
        this._render();
        return;
      }
      ok = await this._swapWeek(row, originalAssigneeId, swapWithId, false);
    }

    if (ok) {
      this._closeSwapModal();
    }
  }

  _bindEvents(weeks, members) {
    if (this._isCompact()) {
      return;
    }

    const weekMap = new Map(weeks.map((row) => [String(row.week_start || ""), row]));

    this._root.querySelectorAll("[data-action='toggle-done']").forEach((el) => {
      el.addEventListener("click", async () => {
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        await this._toggleDone(row, members);
      });
    });

    this._root.querySelectorAll("[data-action='open-swap-modal']").forEach((el) => {
      el.addEventListener("click", () => {
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        this._openSwapModal(row, members);
      });
    });

    this._root.querySelectorAll("[data-action='close-done-modal']").forEach((el) => {
      el.addEventListener("click", () => {
        this._closeDoneModal();
      });
    });

    this._root.querySelectorAll("[name='hf-modal-choice']").forEach((el) => {
      el.addEventListener("change", (event) => {
        this._modalChoice = event.target.value === "takeover" ? "takeover" : "confirm_assignee";
        this._render();
      });
    });

    this._root.querySelector("#hf-modal-cleaner")?.addEventListener("change", (event) => {
      this._modalCleanerMemberId = event.target.value;
      this._render();
    });

    this._root.querySelector("[data-action='submit-done-modal']")?.addEventListener("click", async () => {
      await this._submitDoneModal(weeks, members);
    });

    this._root.querySelector(".done-modal-backdrop")?.addEventListener("click", (event) => {
      if (event.target?.classList?.contains("modal-backdrop")) {
        this._closeDoneModal();
      }
    });

    this._root.querySelectorAll("[data-action='close-swap-modal']").forEach((el) => {
      el.addEventListener("click", () => {
        this._closeSwapModal();
      });
    });

    this._root.querySelectorAll("[name='hf-swap-action']").forEach((el) => {
      el.addEventListener("change", (event) => {
        this._swapModalAction = event.target.value === "cancel" ? "cancel" : "swap";
        this._render();
      });
    });

    this._root.querySelector("#hf-swap-target")?.addEventListener("change", (event) => {
      this._swapTargetMemberId = event.target.value;
      this._render();
    });

    this._root.querySelector("[data-action='submit-swap-modal']")?.addEventListener("click", async () => {
      await this._submitSwapModal(weeks, members);
    });

    this._root.querySelector(".swap-modal-backdrop")?.addEventListener("click", (event) => {
      if (event.target?.classList?.contains("modal-backdrop")) {
        this._closeSwapModal();
      }
    });
  }

  _render() {
    if (!this._config || !this._hass || !this._root) {
      return;
    }

    this._stateObj = this._hass.states[this._config.entity];
    if (!this._stateObj) {
      this._root.innerHTML = `
        <ha-card>
          <div class="empty">Entity not found: <code>${this._escape(this._config.entity)}</code></div>
        </ha-card>
      `;
      return;
    }

    const attrs = this._stateObj.attributes || {};
    const rawWeeks = Array.isArray(attrs.weeks) ? attrs.weeks : [];
    const members = Array.isArray(attrs.members) ? attrs.members : [];
    const memberMap = this._memberMap(members);

    const activeWeekStarts = new Set(rawWeeks.map((row) => String(row.week_start || "")));
    for (const weekStart of [...this._pendingDoneWeeks]) {
      if (!activeWeekStarts.has(weekStart)) {
        this._pendingDoneWeeks.delete(weekStart);
      }
    }
    for (const weekStart of [...this._pendingSwapWeeks]) {
      if (!activeWeekStarts.has(weekStart)) {
        this._pendingSwapWeeks.delete(weekStart);
      }
    }
    for (const weekStart of [...this._optimisticWeekPatches.keys()]) {
      if (!activeWeekStarts.has(weekStart)) {
        this._optimisticWeekPatches.delete(weekStart);
      }
    }

    const rawByWeekStart = new Map(rawWeeks.map((row) => [String(row.week_start || ""), row]));
    for (const [weekStart, patch] of [...this._optimisticWeekPatches.entries()]) {
      const rawRow = rawByWeekStart.get(weekStart);
      if (!rawRow) {
        this._optimisticWeekPatches.delete(weekStart);
        continue;
      }
      const patchApplied = Object.entries(patch).every(
        ([key, value]) => this._normalizePatchValue(rawRow?.[key]) === value
      );
      if (patchApplied) {
        this._optimisticWeekPatches.delete(weekStart);
      }
    }

    const weeksToShow = this._coerceWeeks(this._config.weeks);
    const weeks = rawWeeks
      .slice()
      .map((row) => {
        const weekStart = String(row.week_start || "");
        const patch = this._optimisticWeekPatches.get(weekStart);
        if (!patch) {
          return row;
        }
        return { ...row, ...patch };
      })
      .sort((a, b) => String(a.week_start || "").localeCompare(String(b.week_start || "")))
      .slice(0, weeksToShow);

    const currentWeek = weeks.find((row) => row.is_current) || weeks[0] || null;
    const currentStatus = String(currentWeek?.status || "pending");

    const statusLabel =
      currentStatus === "done" ? "Done" : currentStatus === "missed" ? "Missed" : "Pending";

    const currentAssigneeName =
      currentWeek?.assignee_name ||
      (currentWeek?.assignee_member_id ? `Member ${currentWeek.assignee_member_id}` : "Unassigned");

    const weekRows = weeks
      .map((row, index) => {
        const status = String(row?.status || "pending");
        const isDone = status === "done";
        const isMissed = status === "missed";
        const isCurrent = !!row.is_current;
        const isPrevious = !!row.is_previous;
        const isPast = !!row.is_past;
        const isFuture = !isCurrent && !isPast;
        const canToggle = isCurrent || isPrevious;
        const weekStart = String(row.week_start || "");
        const isDoneSaving = this._pendingDoneWeeks.has(weekStart);
        const isSwapSaving = this._pendingSwapWeeks.has(weekStart);
        const canSwap =
          members.length > 1 &&
          !isPast &&
          !isDone &&
          row.override_type !== "compensation";

        const assigneeMemberId = Number(row.assignee_member_id);
        const assigneeLabel =
          Number.isInteger(assigneeMemberId) && assigneeMemberId > 0
            ? this._memberName(memberMap, assigneeMemberId)
            : row.assignee_name || "Unassigned";
        const assigneeName = this._escape(assigneeLabel);
        const originalMemberId = Number(row.original_assignee_member_id);
        const originalLabel =
          Number.isInteger(originalMemberId) && originalMemberId > 0
            ? this._memberName(memberMap, originalMemberId)
            : row.original_assignee_name || "";
        const originalName = originalLabel ? this._escape(originalLabel) : "";
        const completedByMemberId = Number(row.completed_by_member_id);
        const completedByLabel =
          Number.isInteger(completedByMemberId) && completedByMemberId > 0
            ? this._memberName(memberMap, completedByMemberId)
            : row.completed_by_name || "";
        const completedByName = completedByLabel ? this._escape(completedByLabel) : "";

        let doneMeta = "";
        if (isDone && completedByName) {
          doneMeta = `<span class="meta-note">Done by ${completedByName}</span>`;
        } else if (isMissed) {
          doneMeta = '<span class="meta-note missed">Not confirmed</span>';
        }

        const overrideBadge = row.override_type
          ? `<span class="badge">${this._escape(row.override_type === "manual_swap" ? "Swap" : "Make-up")}</span>`
          : "";

        const secondary =
          row.override_type === "manual_swap" && originalName && originalName !== assigneeName
            ? `<span class="meta-note">Swapped with ${originalName}</span>`
            : row.override_type === "compensation"
              ? `<span class="meta-note">Make-up shift: ${assigneeName} covers ${originalName || "the original turn"}</span>`
              : "";

        const actionParts = [];
        if (canToggle) {
          actionParts.push(`<button
               class="action ${isDone ? "undo" : "done"}"
               type="button"
               data-action="toggle-done"
               data-week-start="${this._escape(row.week_start)}"
               ${isDoneSaving || isSwapSaving ? "disabled" : ""}
             >
               <ha-icon icon="${isDone ? "mdi:undo-variant" : "mdi:check-circle-outline"}"></ha-icon>
               <span>${isDoneSaving ? "Saving..." : isDone ? "Undo" : "Mark done"}</span>
             </button>`);
        } else {
          const futureLabel = isFuture ? "Upcoming" : "Pending";
          if (!canSwap || isDone || isMissed) {
            actionParts.push(`<span class="status-chip ${isDone ? "done" : isMissed ? "missed" : "pending"}">
                 ${isDone ? "Done" : isMissed ? "Missed" : futureLabel}
               </span>`);
          }
        }

        if (canSwap) {
          const swapLabel = row.override_type === "manual_swap" ? "Edit swap" : "Swap";
          actionParts.push(`<button
               class="action swap"
               type="button"
               data-action="open-swap-modal"
               data-week-start="${this._escape(row.week_start)}"
               ${isDoneSaving || isSwapSaving ? "disabled" : ""}
             >
               <ha-icon icon="mdi:swap-horizontal"></ha-icon>
               <span>${isSwapSaving ? "Saving..." : swapLabel}</span>
             </button>`);
        }

        const actionControl = actionParts.join("");

        return `
          <li class="week-row ${isCurrent ? "current" : ""} ${isPast ? "past" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}">
            <div class="week-main">
              <div class="week-top">
                <span class="week-label">${this._escape(this._weekTitle(row, index))}</span>
                <span class="week-dates">${this._escape(this._rowDateRange(row))}</span>
              </div>
              <div class="assignee ${isDone ? "striked" : ""}">
                ${isDone ? '<ha-icon icon="mdi:check"></ha-icon>' : ""}
                <span>${assigneeName}</span>
                ${overrideBadge}
              </div>
              <div class="week-meta">
                ${secondary}
                ${doneMeta}
              </div>
            </div>
            <div class="week-actions">
              ${actionControl}
            </div>
          </li>
        `;
      })
      .join("");

    const compactMode = this._isCompact();
    const errorMessage = this._errorMessage ? this._escape(this._errorMessage) : "";
    const modalWeek = this._resolveModalWeek(weeks);
    const modalAssigneeId = Number(this._modalAssigneeMemberId || modalWeek?.assignee_member_id);
    const modalAssigneeName = this._memberName(memberMap, modalAssigneeId);
    const modalCleanerId = Number(this._modalCleanerMemberId);
    const hasValidModalCleaner =
      Number.isInteger(modalCleanerId) && modalCleanerId > 0 && modalCleanerId !== modalAssigneeId;
    const modalCleanerName = hasValidModalCleaner
      ? this._memberName(memberMap, modalCleanerId)
      : "the selected flatmate";
    const modalCompensationWeek =
      this._modalChoice === "takeover" && hasValidModalCleaner
        ? this._findCompensationPreviewWeek(weeks, modalCleanerId, modalWeek?.week_start)
        : null;
    const modalCompensationWeekIndex = modalCompensationWeek
      ? weeks.findIndex((row) => row.week_start === modalCompensationWeek.week_start)
      : -1;
    const modalCompensationWeekLabel = modalCompensationWeek
      ? `${this._weekTitle(
          modalCompensationWeek,
          modalCompensationWeekIndex >= 0 ? modalCompensationWeekIndex : 0
        )} (${this._rowDateRange(modalCompensationWeek)})`
      : "the next eligible original shift in the visible schedule";

    const doneEffectsHtml =
      this._modalChoice === "takeover"
        ? `
          <ul class="effect-list">
            <li>Record that <strong>${this._escape(modalCleanerName)}</strong> took over this shift from <strong>${this._escape(modalAssigneeName)}</strong>.</li>
            <li>Automatically assign <strong>${this._escape(modalAssigneeName)}</strong> to <strong>${this._escape(modalCleanerName)}</strong>'s next original turn in <strong>${this._escape(modalCompensationWeekLabel)}</strong>.</li>
            <li>Send a notification to both flatmates with the takeover and make-up shift details.</li>
          </ul>
        `
        : `
          <ul class="effect-list">
            <li>Mark this shift as done for <strong>${this._escape(modalAssigneeName)}</strong>.</li>
            <li>Send a notification to <strong>${this._escape(modalAssigneeName)}</strong> that you confirmed completion.</li>
          </ul>
        `;

    const cleanerOptions = [
      `<option value="" ${hasValidModalCleaner ? "" : "selected"} disabled>Select who cleaned</option>`,
      ...members.map((member) => {
        const memberId = Number(member?.member_id);
        if (!Number.isInteger(memberId) || memberId <= 0 || memberId === modalAssigneeId) {
          return "";
        }
        const name = this._escape(member?.name || `Member ${memberId}`);
        return `<option value="${memberId}">${name}</option>`;
      }),
    ].join("");

    const swapModalWeek = this._resolveSwapModalWeek(weeks);
    const swapOriginalAssigneeId = Number(
      this._swapOriginalAssigneeMemberId ||
      swapModalWeek?.original_assignee_member_id ||
      swapModalWeek?.assignee_member_id
    );
    const swapOriginalAssigneeName = this._memberName(memberMap, swapOriginalAssigneeId);
    const swapHasExistingManualSwap = swapModalWeek?.override_type === "manual_swap";
    const swapExistingPartnerId = Number(swapModalWeek?.assignee_member_id);
    const swapTargetId = Number(this._swapTargetMemberId || "");
    const hasValidSwapTarget =
      Number.isInteger(swapTargetId) && swapTargetId > 0 && swapTargetId !== swapOriginalAssigneeId;
    const swapTargetName = hasValidSwapTarget
      ? this._memberName(memberMap, swapTargetId)
      : "the selected flatmate";
    const swapWeekIndex = swapModalWeek
      ? weeks.findIndex((row) => row.week_start === swapModalWeek.week_start)
      : -1;
    const swapWeekLabel = swapModalWeek
      ? `${this._weekTitle(swapModalWeek, swapWeekIndex >= 0 ? swapWeekIndex : 0)} (${this._rowDateRange(swapModalWeek)})`
      : "the selected week";
    const swapCancelPartnerName =
      Number.isInteger(swapExistingPartnerId) &&
      swapExistingPartnerId > 0 &&
      swapExistingPartnerId !== swapOriginalAssigneeId
        ? this._memberName(memberMap, swapExistingPartnerId)
        : "the swap partner";
    const swapEffectsHtml =
      this._swapModalAction === "cancel"
        ? `
          <ul class="effect-list">
            <li>Restore the original assignment for <strong>${this._escape(swapOriginalAssigneeName)}</strong> in <strong>${this._escape(swapWeekLabel)}</strong>.</li>
            <li>Send a notification to <strong>${this._escape(swapOriginalAssigneeName)}</strong> and <strong>${this._escape(swapCancelPartnerName)}</strong> that the swap was canceled.</li>
          </ul>
        `
        : `
          <ul class="effect-list">
            <li>Swap <strong>${this._escape(swapOriginalAssigneeName)}</strong> with <strong>${this._escape(swapTargetName)}</strong> for <strong>${this._escape(swapWeekLabel)}</strong>.</li>
            <li>Send a notification to both flatmates with the week and original assignee details.</li>
          </ul>
        `;
    const swapTargetOptions = [
      `<option value="" ${hasValidSwapTarget ? "" : "selected"} disabled>Select flatmate</option>`,
      ...members.map((member) => {
        const memberId = Number(member?.member_id);
        if (!Number.isInteger(memberId) || memberId <= 0 || memberId === swapOriginalAssigneeId) {
          return "";
        }
        const name = this._escape(member?.name || `Member ${memberId}`);
        return `<option value="${memberId}">${name}</option>`;
      }),
    ].join("");

    const compactRows = weeks
      .map((row) => {
        const status = String(row?.status || "pending");
        const isDone = status === "done";
        const isMissed = status === "missed";
        const compactStatusLabel = isDone
          ? "Done"
          : isMissed
            ? "Missed"
            : row.is_current
              ? "Pending"
              : "";
        const compactStatusClass = isDone ? "done" : isMissed ? "missed" : "pending";
        const compactContext = row.is_current
          ? "this week"
          : row.is_previous
            ? "previous week"
            : row.is_next
              ? "next week"
              : "";
        const compactDateLabel = this._escape(this._rowDateRange(row));
        const compactContextHtml = compactContext
          ? ` <span class="compact-context">(${this._escape(compactContext)})</span>`
          : "";

        const assigneeMemberId = Number(row.assignee_member_id);
        const assigneeLabel =
          Number.isInteger(assigneeMemberId) && assigneeMemberId > 0
            ? this._memberName(memberMap, assigneeMemberId)
            : row.assignee_name || "Unassigned";
        const assigneeName = this._escape(assigneeLabel);
        const originalMemberId = Number(row.original_assignee_member_id);
        const originalLabel =
          Number.isInteger(originalMemberId) && originalMemberId > 0
            ? this._memberName(memberMap, originalMemberId)
            : row.original_assignee_name || "";
        const originalName = originalLabel ? this._escape(originalLabel) : "";
        const completedByMemberId = Number(row.completed_by_member_id);
        const completedByName =
          Number.isInteger(completedByMemberId) && completedByMemberId > 0
            ? this._escape(this._memberName(memberMap, completedByMemberId))
            : row.completed_by_name
              ? this._escape(row.completed_by_name)
              : "";

        let compactNote = "";
        if (row.override_type === "manual_swap" && originalName && originalName !== assigneeName) {
          compactNote = `Swapped with ${originalName}`;
        } else if (row.override_type === "compensation") {
          compactNote = `Make-up shift: ${assigneeName} covers ${originalName || "the original turn"}`;
        } else if (isDone && completedByName) {
          compactNote = `Done by ${completedByName}`;
        } else if (isMissed) {
          compactNote = "Not confirmed";
        }

        return `
          <li class="compact-week-row ${row.is_current ? "current" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}">
            <div class="compact-top">
              <span class="compact-assignee">${assigneeName}</span>
              ${
                compactStatusLabel
                  ? `<span class="compact-status ${compactStatusClass}">${compactStatusLabel}</span>`
                  : ""
              }
            </div>
            <span class="compact-week"><span class="compact-date">${compactDateLabel}</span>${compactContextHtml}</span>
            ${compactNote ? `<span class="compact-note">${this._escape(compactNote)}</span>` : ""}
          </li>
        `;
      })
      .join("");

    this._root.innerHTML = `
      <ha-card>
        <div class="card ${compactMode ? "compact" : ""}">
          ${
            compactMode
              ? `
                <div class="header compact-header">
                  <h2>${this._escape(this._config.title)}</h2>
                </div>
              `
              : `
                <div class="header">
                  <div>
                    <h2>${this._escape(this._config.title)}</h2>
                    <p>${this._escape(currentAssigneeName)} • ${statusLabel}</p>
                  </div>
                  <span class="header-status ${currentStatus}">${statusLabel}</span>
                </div>
              `
          }

          <section>
            ${compactMode ? "" : "<h3>Schedule</h3>"}
            ${
              compactMode
                ? `
                  <ul class="compact-week-list">
                    ${compactRows || '<li class="empty-list">No schedule data yet</li>'}
                  </ul>
                `
                : `
                  <ul class="week-list">
                    ${weekRows || '<li class="empty-list">No schedule data yet</li>'}
                  </ul>
                `
            }
          </section>

          ${!compactMode && errorMessage ? `<div class="error">${errorMessage}</div>` : ""}
        </div>

        ${!compactMode && this._modalOpen && modalWeek ? `
          <div class="modal-backdrop done-modal-backdrop">
            <div class="modal" role="dialog" aria-modal="true">
              <div class="modal-header">
                <h3>Confirm cleaning completion</h3>
                <button class="icon-btn" type="button" data-action="close-done-modal" aria-label="Close confirmation dialog">
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>

              <p class="modal-week">${this._escape(this._weekTitle(modalWeek, 0))} • ${this._escape(this._rowDateRange(modalWeek))}</p>
              <p class="modal-preview">Original assignee: <strong>${this._escape(modalAssigneeName)}</strong></p>

              <div class="choice-group">
                <label class="choice-option">
                  <input type="radio" name="hf-modal-choice" value="confirm_assignee" ${this._modalChoice !== "takeover" ? "checked" : ""} />
                  <span>${this._escape(modalAssigneeName)} cleaned. I am confirming it for them.</span>
                </label>
                <p class="choice-help">
                  Use this if you are only confirming completion on their behalf.
                </p>

                <label class="choice-option">
                  <input type="radio" name="hf-modal-choice" value="takeover" ${this._modalChoice === "takeover" ? "checked" : ""} />
                  <span>Someone else cleaned and took over this shift.</span>
                </label>
                <p class="choice-help">
                  Use takeover when another flatmate actually cleaned so a make-up shift is planned automatically.
                </p>
              </div>

              ${
                this._modalChoice === "takeover"
                  ? `
                    <label for="hf-modal-cleaner">Who cleaned this week?</label>
                    <select id="hf-modal-cleaner">
                      ${cleanerOptions}
                    </select>
                  `
                  : ""
              }

              <div class="effect-panel">
                <p class="effect-title">What this will do</p>
                ${doneEffectsHtml}
              </div>

              <div class="modal-actions">
                <button class="btn secondary" type="button" data-action="close-done-modal">Close</button>
                <button class="btn primary" type="button" data-action="submit-done-modal">
                  ${this._modalChoice === "takeover" ? "Confirm takeover" : "Confirm done"}
                </button>
              </div>
            </div>
          </div>
        ` : ""}

        ${!compactMode && this._swapModalOpen && swapModalWeek ? `
          <div class="modal-backdrop swap-modal-backdrop">
            <div class="modal" role="dialog" aria-modal="true">
              <div class="modal-header">
                <h3>${swapHasExistingManualSwap ? "Edit weekly swap" : "Schedule weekly swap"}</h3>
                <button class="icon-btn" type="button" data-action="close-swap-modal" aria-label="Close swap dialog">
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>

              <p class="modal-week">${this._escape(swapWeekLabel)}</p>
              <p class="modal-preview">Original assignee: <strong>${this._escape(swapOriginalAssigneeName)}</strong></p>

              <label for="hf-swap-target">Swap with</label>
              <select id="hf-swap-target" ${this._swapModalAction === "cancel" ? "disabled" : ""}>
                ${swapTargetOptions}
              </select>

              <div class="choice-group">
                <label class="choice-option">
                  <input type="radio" name="hf-swap-action" value="swap" ${this._swapModalAction !== "cancel" ? "checked" : ""} />
                  <span>${swapHasExistingManualSwap ? "Update swap for this week" : "Create swap for this week"}</span>
                </label>
                <p class="choice-help">
                  Both involved flatmates will be notified immediately.
                </p>
                ${
                  swapHasExistingManualSwap
                    ? `
                      <label class="choice-option">
                        <input type="radio" name="hf-swap-action" value="cancel" ${this._swapModalAction === "cancel" ? "checked" : ""} />
                        <span>Cancel existing swap</span>
                      </label>
                      <p class="choice-help">
                        Restores the original assignment and notifies both flatmates.
                      </p>
                    `
                    : ""
                }
              </div>

              <div class="effect-panel">
                <p class="effect-title">What this will do</p>
                ${swapEffectsHtml}
              </div>

              <div class="modal-actions">
                <button class="btn secondary" type="button" data-action="close-swap-modal">Close</button>
                <button class="btn primary" type="button" data-action="submit-swap-modal">
                  ${this._swapModalAction === "cancel" ? "Cancel swap" : swapHasExistingManualSwap ? "Save swap changes" : "Create swap"}
                </button>
              </div>
            </div>
          </div>
        ` : ""}
      </ha-card>

      <style>
        .card {
          padding: 16px;
          display: grid;
          gap: 14px;
        }

        .card.compact {
          padding: 12px;
          gap: 10px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
        }

        .header h2 {
          margin: 0;
          font-size: 1.2rem;
          line-height: 1.25;
        }

        .compact-header {
          justify-content: flex-start;
        }

        .card.compact .header h2 {
          font-size: 1.05rem;
        }

        .header p {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }

        .card.compact .header p {
          font-size: 0.82rem;
        }

        .header-status {
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 0.78rem;
          border: 1px solid var(--divider-color);
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .card.compact .header-status {
          font-size: 0.72rem;
          padding: 5px 8px;
        }

        .header-status.done {
          color: var(--success-color, #4caf50);
          background: color-mix(in srgb, var(--success-color, #4caf50) 14%, var(--card-background-color));
          border-color: color-mix(in srgb, var(--success-color, #4caf50) 40%, var(--divider-color));
        }

        .header-status.missed {
          color: var(--warning-color, #f57c00);
          background: color-mix(in srgb, var(--warning-color, #f57c00) 14%, var(--card-background-color));
          border-color: color-mix(in srgb, var(--warning-color, #f57c00) 40%, var(--divider-color));
        }

        .header-status.pending {
          color: var(--primary-text-color);
        }

        section h3 {
          margin: 0 0 8px;
          font-size: 0.92rem;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .week-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 8px;
        }

        .week-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 10px;
          align-items: center;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          padding: 10px;
        }

        .compact-week-list {
          list-style: none;
          margin: 0;
          padding: 0;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          overflow: hidden;
          background: var(--card-background-color);
          display: grid;
        }

        .compact-week-row {
          display: grid;
          gap: 4px;
          align-items: start;
          padding: 8px 10px;
          border-bottom: 1px solid var(--divider-color);
          font-size: 0.83rem;
          line-height: 1.25;
        }

        .compact-week-row:last-child {
          border-bottom: none;
        }

        .compact-week-row.current {
          border-left: 3px solid var(--primary-text-color);
          padding-left: 7px;
          font-weight: 700;
        }

        .compact-top {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 8px;
        }

        .compact-week {
          color: var(--secondary-text-color);
          min-width: 0;
          overflow-wrap: anywhere;
        }

        .compact-date {
          font-style: normal;
        }

        .compact-context {
          font-style: italic;
        }

        .compact-week-row.current .compact-week {
          color: var(--primary-text-color);
        }

        .compact-assignee {
          font-weight: 700;
          font-size: 0.9rem;
          line-height: 1.2;
        }

        .compact-status {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 2px 8px;
          text-transform: uppercase;
          font-size: 0.72rem;
          white-space: nowrap;
        }

        .compact-week-row.done .compact-status {
          color: var(--success-color, #4caf50);
        }

        .compact-week-row.missed .compact-status {
          color: var(--warning-color, #f57c00);
        }

        .compact-note {
          color: var(--secondary-text-color);
          font-size: 0.78rem;
          font-style: italic;
          text-align: left;
        }

        .week-row.current {
          border-color: color-mix(in srgb, var(--primary-color) 45%, var(--divider-color));
          background: color-mix(in srgb, var(--primary-color) 8%, var(--card-background-color));
        }

        .week-row.past {
          background: color-mix(in srgb, var(--secondary-text-color) 6%, var(--card-background-color));
        }

        .week-top {
          display: flex;
          align-items: baseline;
          gap: 8px;
          flex-wrap: wrap;
        }

        .week-label {
          font-weight: 700;
          font-size: 0.88rem;
        }

        .week-dates {
          color: var(--secondary-text-color);
          font-size: 0.82rem;
        }

        .assignee {
          margin-top: 4px;
          display: flex;
          align-items: center;
          gap: 6px;
          font-weight: 600;
          min-width: 0;
        }

        .assignee.striked span {
          text-decoration: line-through;
          text-decoration-thickness: 1.5px;
          text-decoration-color: color-mix(in srgb, var(--success-color, #4caf50) 65%, currentColor);
        }

        .week-meta {
          margin-top: 4px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .meta-note {
          color: var(--secondary-text-color);
          font-size: 0.78rem;
        }

        .meta-note.missed {
          color: var(--warning-color, #f57c00);
        }

        .badge {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 0.72rem;
          font-weight: 600;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .week-actions {
          display: flex;
          flex-direction: column;
          gap: 6px;
          align-items: stretch;
        }

        .action,
        .status-chip,
        .btn,
        .icon-btn {
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 10px;
          font: inherit;
        }

        .action {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          justify-content: center;
          padding: 7px 10px;
          cursor: pointer;
          min-height: 36px;
          white-space: nowrap;
        }

        .action.done {
          color: var(--success-color, #4caf50);
          border-color: color-mix(in srgb, var(--success-color, #4caf50) 40%, var(--divider-color));
          background: color-mix(in srgb, var(--success-color, #4caf50) 10%, var(--card-background-color));
        }

        .action.undo {
          color: var(--secondary-text-color);
        }

        .action.swap {
          color: var(--primary-color);
          border-color: color-mix(in srgb, var(--primary-color) 35%, var(--divider-color));
          background: color-mix(in srgb, var(--primary-color) 8%, var(--card-background-color));
        }

        .status-chip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 34px;
          padding: 0 10px;
          font-size: 0.78rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .status-chip.done {
          color: var(--success-color, #4caf50);
        }

        .status-chip.missed {
          color: var(--warning-color, #f57c00);
        }

        .action:hover,
        .btn:hover,
        .icon-btn:hover {
          border-color: var(--primary-color);
        }

        .action:disabled,
        .btn:disabled {
          opacity: 0.55;
          cursor: default;
        }

        .error {
          border: 1px solid color-mix(in srgb, var(--error-color, #f44336) 40%, var(--divider-color));
          color: var(--error-color, #f44336);
          background: color-mix(in srgb, var(--error-color, #f44336) 8%, var(--card-background-color));
          border-radius: 10px;
          padding: 8px 10px;
          font-size: 0.9rem;
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
        }

        .modal-backdrop {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.38);
          display: grid;
          place-items: center;
          z-index: 20;
          padding: 14px;
          box-sizing: border-box;
        }

        .modal {
          width: min(560px, 100%);
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          box-shadow: 0 12px 36px rgba(0, 0, 0, 0.3);
          padding: 14px;
          display: grid;
          gap: 10px;
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
        }

        .modal-header h3 {
          margin: 0;
          font-size: 1.03rem;
        }

        .icon-btn {
          cursor: pointer;
          width: 34px;
          height: 34px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 0;
        }

        .modal-week {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }

        label {
          font-size: 0.84rem;
          color: var(--secondary-text-color);
        }

        select {
          box-sizing: border-box;
          width: 100%;
          min-height: 40px;
          border-radius: 10px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          padding: 8px 10px;
        }

        select:disabled {
          opacity: 0.65;
          cursor: default;
        }

        .modal-preview {
          margin: 2px 0 0;
          font-size: 0.88rem;
          color: var(--secondary-text-color);
        }

        .choice-group {
          display: grid;
          gap: 6px;
          border: 1px solid var(--divider-color);
          border-radius: 10px;
          padding: 10px;
        }

        .choice-option {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          color: var(--primary-text-color);
          font-size: 0.92rem;
        }

        .choice-option input {
          margin-top: 2px;
        }

        .choice-help {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.82rem;
          padding-left: 26px;
        }

        .effect-panel {
          border: 1px solid var(--divider-color);
          border-radius: 10px;
          padding: 10px;
          background: color-mix(in srgb, var(--divider-color) 8%, var(--card-background-color));
          display: grid;
          gap: 6px;
        }

        .effect-title {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .effect-list {
          margin: 0;
          padding-left: 18px;
          display: grid;
          gap: 4px;
          font-size: 0.9rem;
          line-height: 1.35;
        }

        .effect-list strong {
          font-weight: 700;
        }

        .modal-actions {
          display: flex;
          flex-wrap: wrap;
          justify-content: flex-end;
          gap: 8px;
          margin-top: 4px;
        }

        .btn {
          cursor: pointer;
          min-height: 36px;
          padding: 8px 12px;
        }

        .btn.primary {
          color: var(--primary-color);
          border-color: color-mix(in srgb, var(--primary-color) 40%, var(--divider-color));
          background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
        }

        @media (max-width: 720px) {
          .week-row {
            grid-template-columns: 1fr;
          }

          .week-actions {
            flex-direction: row;
            justify-content: flex-start;
          }

          .action,
          .status-chip {
            flex: 1 1 auto;
          }

          .modal-actions {
            justify-content: stretch;
          }

          .btn {
            flex: 1 1 auto;
          }

          .compact-week-row {
            gap: 2px;
          }

          .compact-top {
            flex-direction: column;
            align-items: flex-start;
          }
        }
      </style>
    `;

    const modalCleanerSelect = this._root.querySelector("#hf-modal-cleaner");
    if (modalCleanerSelect && this._modalCleanerMemberId) {
      modalCleanerSelect.value = this._modalCleanerMemberId;
    }
    const swapTargetSelect = this._root.querySelector("#hf-swap-target");
    if (swapTargetSelect && this._swapTargetMemberId) {
      swapTargetSelect.value = this._swapTargetMemberId;
    }

    this._bindEvents(weeks, members);
  }
}

class HassFlatmateCleaningCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._editorReady = false;
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_cleaning_schedule",
      title: "Cleaning Rotation",
      weeks: 5,
      layout: "interactive",
      ...config,
    };
    this._render();
    this._syncEditorValues();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
    this._syncEditorValues();
  }

  _emitConfig(config) {
    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this._hass || !this._config || !this._root) {
      return;
    }
    if (this._editorReady) {
      return;
    }

    this._root.innerHTML = `
      <div class="editor">
        <label for="hf-editor-title">Card title</label>
        <input id="hf-editor-title" type="text" value="${this._config.title || ""}" />

        <label for="hf-editor-entity">Schedule entity</label>
        <ha-entity-picker id="hf-editor-entity"></ha-entity-picker>

        <label for="hf-editor-weeks">Weeks shown (3-12)</label>
        <input id="hf-editor-weeks" type="number" min="3" max="12" value="${Number.parseInt(this._config.weeks, 10) || 5}" />

        <label for="hf-editor-layout">Card style</label>
        <select id="hf-editor-layout">
          <option value="interactive" ${this._config.layout === "compact" ? "" : "selected"}>Interactive</option>
          <option value="compact" ${this._config.layout === "compact" ? "selected" : ""}>Compact (read-only)</option>
        </select>
      </div>

      <style>
        .editor {
          display: grid;
          gap: 10px;
          padding: 8px 0;
        }

        .editor label {
          color: var(--secondary-text-color);
          font-size: 0.9rem;
          margin-bottom: -4px;
        }

        .editor input {
          box-sizing: border-box;
          width: 100%;
          min-height: 40px;
          border-radius: 10px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          padding: 8px 10px;
        }

        .editor select {
          box-sizing: border-box;
          width: 100%;
          min-height: 40px;
          border-radius: 10px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          padding: 8px 10px;
        }
      </style>
    `;

    const titleInput = this._root.querySelector("#hf-editor-title");
    titleInput?.addEventListener("input", (event) => {
      this._emitConfig({
        ...this._config,
        title: event.target.value,
      });
    });

    const weeksInput = this._root.querySelector("#hf-editor-weeks");
    weeksInput?.addEventListener("input", (event) => {
      const value = Number.parseInt(event.target.value, 10);
      const weeks = Number.isInteger(value) ? Math.max(3, Math.min(12, value)) : 5;
      this._emitConfig({
        ...this._config,
        weeks,
      });
    });

    const entityPicker = this._root.querySelector("#hf-editor-entity");
    if (entityPicker) {
      entityPicker.includeDomains = ["sensor"];
      entityPicker.addEventListener("value-changed", (event) => {
        const nextValue = event.detail?.value;
        if (!nextValue) {
          return;
        }
        this._emitConfig({
          ...this._config,
          entity: nextValue,
        });
      });
    }

    const layoutInput = this._root.querySelector("#hf-editor-layout");
    layoutInput?.addEventListener("change", (event) => {
      this._emitConfig({
        ...this._config,
        layout: event.target.value || "interactive",
      });
    });
    this._editorReady = true;
  }

  _syncEditorValues() {
    if (!this._editorReady || !this._config || !this._hass) {
      return;
    }

    const active = this._root.activeElement;

    const titleInput = this._root.querySelector("#hf-editor-title");
    if (titleInput && active !== titleInput) {
      titleInput.value = this._config.title || "";
    }

    const weeksInput = this._root.querySelector("#hf-editor-weeks");
    if (weeksInput && active !== weeksInput) {
      const nextWeeks = Number.parseInt(this._config.weeks, 10) || 5;
      if (Number.parseInt(weeksInput.value, 10) !== nextWeeks) {
        weeksInput.value = String(nextWeeks);
      }
    }

    const entityPicker = this._root.querySelector("#hf-editor-entity");
    if (entityPicker) {
      entityPicker.hass = this._hass;
      const nextEntity = this._config.entity || "sensor.hass_flatmate_cleaning_schedule";
      if (entityPicker.value !== nextEntity) {
        entityPicker.value = nextEntity;
      }
    }

    const layoutInput = this._root.querySelector("#hf-editor-layout");
    if (layoutInput && active !== layoutInput) {
      const nextLayout = this._config.layout === "compact" ? "compact" : "interactive";
      if (layoutInput.value !== nextLayout) {
        layoutInput.value = nextLayout;
      }
    }
  }
}

if (!customElements.get("hass-flatmate-cleaning-card")) {
  customElements.define("hass-flatmate-cleaning-card", HassFlatmateCleaningCard);
}
if (!customElements.get("hass-flatmate-cleaning-card-editor")) {
  customElements.define("hass-flatmate-cleaning-card-editor", HassFlatmateCleaningCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hass-flatmate-cleaning-card")) {
  window.customCards.push({
    type: "hass-flatmate-cleaning-card",
    name: "Hass Flatmate Cleaning Card",
    description: "Cleaning schedule card with interactive and compact read-only layouts.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#cleaning-ui-card",
  });
}
