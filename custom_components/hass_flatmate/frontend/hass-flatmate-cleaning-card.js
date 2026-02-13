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
    this._historyModalOpen = false;
    this._historyModalWeekStart = "";
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
      history_modal_open: this._historyModalOpen,
      history_modal_week_start: this._historyModalWeekStart,
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

  _resolveHistoryModalWeek(weeks) {
    if (!this._historyModalWeekStart) {
      return null;
    }
    return weeks.find((row) => row.week_start === this._historyModalWeekStart) || null;
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

  _weekDistanceLabel(targetWeekStart, currentWeekStart) {
    const target = this._parseWeekDate(targetWeekStart);
    const current = this._parseWeekDate(currentWeekStart);
    if (!target || !current) {
      return "";
    }
    const diffWeeks = Math.round((target.getTime() - current.getTime()) / (7 * 24 * 60 * 60 * 1000));
    if (diffWeeks === 0) {
      return "this week";
    }
    if (diffWeeks === 1) {
      return "in 1 week";
    }
    if (diffWeeks > 1) {
      return `in ${diffWeeks} weeks`;
    }
    if (diffWeeks === -1) {
      return "1 week ago";
    }
    return `${Math.abs(diffWeeks)} weeks ago`;
  }

  _formatWeekLabelWithDistance(row, index, currentWeekStart) {
    if (!row) {
      return "selected week";
    }
    const range = this._rowDateRange(row);
    const distance = this._weekDistanceLabel(row?.week_start, currentWeekStart);
    if (distance) {
      return `${distance} (${range})`;
    }
    return `${this._weekTitle(row, index)} (${range})`;
  }

  _formatEventDateTime(value) {
    if (!value) {
      return "";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return String(value);
    }
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
  }

  _compensationNote(row, assigneeLabel, originalLabel) {
    if (row?.override_type !== "compensation") {
      return "";
    }

    if (row?.override_source === "manual") {
      const swappedWith = originalLabel || "another flatmate";
      const elapsed = this._weekDistanceLabel(row?.source_week_start, row?.week_start);
      return elapsed
        ? `Swap return — ${swappedWith}'s regular week (${elapsed})`
        : `Swap return — ${swappedWith}'s regular week`;
    }

    return `Return shift for ${originalLabel || "the original assignee"}`;
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

  _findExistingManualSwapReturnWeek(weeks, originalMemberId, targetMemberId, sourceWeekStart) {
    if (!Number.isInteger(originalMemberId) || originalMemberId <= 0) {
      return null;
    }
    if (!Number.isInteger(targetMemberId) || targetMemberId <= 0) {
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
      if (row?.override_type !== "compensation" || row?.override_source !== "manual") {
        continue;
      }
      const effectiveId = Number(row?.assignee_member_id);
      const baselineId = Number(row?.original_assignee_member_id ?? row?.baseline_assignee_member_id);
      if (
        Number.isInteger(effectiveId) &&
        Number.isInteger(baselineId) &&
        effectiveId === originalMemberId &&
        baselineId === targetMemberId
      ) {
        return row;
      }
    }

    return null;
  }

  _findSwapReturnPreviewWeek(weeks, originalMemberId, targetMemberId, sourceWeekStart) {
    return (
      this._findExistingManualSwapReturnWeek(
        weeks,
        originalMemberId,
        targetMemberId,
        sourceWeekStart
      ) || this._findCompensationPreviewWeek(weeks, targetMemberId, sourceWeekStart)
    );
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

  _openHistoryModal(weekRow) {
    if (!weekRow || !weekRow.week_start) {
      return;
    }
    this._historyModalOpen = true;
    this._historyModalWeekStart = String(weekRow.week_start);
    this._modalOpen = false;
    this._swapModalOpen = false;
    this._errorMessage = "";
    this._render();
  }

  _closeHistoryModal() {
    this._historyModalOpen = false;
    this._historyModalWeekStart = "";
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
    this._historyModalOpen = false;
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
    this._historyModalOpen = false;
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

  async _cancelLinkedSwap(row, weeks) {
    if (!row || row.override_type !== "compensation") {
      return;
    }
    const compensationWeekStart = String(row.week_start || "");
    const sourceWeekStart = row.source_week_start;
    if (!sourceWeekStart) {
      this._errorMessage = "Cannot find the linked swap week.";
      this._render();
      return;
    }
    const sourceRow = weeks.find(
      (w) => w.override_type === "manual_swap" && String(w.week_start || "") === String(sourceWeekStart)
    );
    if (!sourceRow) {
      this._errorMessage = "The original swap week is no longer visible.";
      this._render();
      return;
    }
    const originalAssigneeId = Number(
      sourceRow.original_assignee_member_id ?? sourceRow.baseline_assignee_member_id
    );
    const swappedWithId = Number(sourceRow.assignee_member_id);
    if (
      !Number.isInteger(originalAssigneeId) ||
      originalAssigneeId <= 0 ||
      !Number.isInteger(swappedWithId) ||
      swappedWithId <= 0 ||
      originalAssigneeId === swappedWithId
    ) {
      this._errorMessage = "Cannot resolve the swap participants.";
      this._render();
      return;
    }
    // Optimistic UI for the compensation week (reverts to original assignee)
    const memberMap = this._memberMap(Array.isArray(this._stateObj?.attributes?.members) ? this._stateObj.attributes.members : []);
    const compensationOriginalId = Number(row.original_assignee_member_id ?? row.baseline_assignee_member_id);
    if (compensationWeekStart) {
      this._pendingSwapWeeks.add(compensationWeekStart);
      this._setWeekPatch(compensationWeekStart, {
        override_type: null,
        assignee_member_id: compensationOriginalId,
        assignee_name: this._memberName(memberMap, compensationOriginalId),
      });
      this._render();
    }
    try {
      await this._swapWeek(sourceRow, originalAssigneeId, swappedWithId, true);
    } finally {
      this._pendingSwapWeeks.delete(compensationWeekStart);
      this._render();
    }
  }

  _bindEvents(weeks, members) {
    if (this._isCompact()) {
      return;
    }

    const weekMap = new Map(weeks.map((row) => [String(row.week_start || ""), row]));

    this._root.querySelectorAll("[data-action='open-history-modal']").forEach((el) => {
      const openHistory = () => {
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        this._openHistoryModal(row);
      };
      el.addEventListener("click", openHistory);
      el.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openHistory();
        }
      });
    });

    this._root.querySelectorAll("[data-action='toggle-done']").forEach((el) => {
      el.addEventListener("click", async (event) => {
        event.stopPropagation();
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        if (!row) return;
        const status = String(row.status || "pending");
        const isNonAssignee = status !== "done" && this._isNonAssignee(row, members);
        if (!isNonAssignee) {
          const prompt = status === "done"
            ? "Undo completion for this week?"
            : "Mark this week as done?";
          if (!window.confirm(prompt)) return;
        }
        await this._toggleDone(row, members);
      });
    });

    this._root.querySelectorAll("[data-action='open-swap-modal']").forEach((el) => {
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        this._openSwapModal(row, members);
      });
    });

    this._root.querySelectorAll("[data-action='cancel-linked-swap']").forEach((el) => {
      el.addEventListener("click", async (event) => {
        event.stopPropagation();
        const weekStart = String(el.dataset.weekStart || "");
        const row = weekMap.get(weekStart);
        await this._cancelLinkedSwap(row, weeks);
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

    this._root.querySelectorAll("[data-action='close-history-modal']").forEach((el) => {
      el.addEventListener("click", () => {
        this._closeHistoryModal();
      });
    });

    this._root.querySelector(".history-modal-backdrop")?.addEventListener("click", (event) => {
      if (event.target?.classList?.contains("modal-backdrop")) {
        this._closeHistoryModal();
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
    const scheduleWeeks = rawWeeks
      .slice()
      .map((row) => {
        const weekStart = String(row.week_start || "");
        const patch = this._optimisticWeekPatches.get(weekStart);
        if (!patch) {
          return row;
        }
        return { ...row, ...patch };
      })
      .sort((a, b) => String(a.week_start || "").localeCompare(String(b.week_start || "")));
    const weeks = scheduleWeeks.slice(0, weeksToShow);

    const currentWeek =
      scheduleWeeks.find((row) => row.is_current) || weeks[0] || scheduleWeeks[0] || null;

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
        const isCompensation = row.override_type === "compensation";
        const sourceSwapDone = isCompensation && row.source_week_start
          ? weeks.some((w) => w.override_type === "manual_swap" && String(w.week_start || "") === String(row.source_week_start) && String(w.status || "") === "done")
          : false;
        const canSwap =
          members.length > 1 &&
          !isPast &&
          !isDone &&
          (!isCompensation || sourceSwapDone);

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
        const completedByMemberId = Number(row.completed_by_member_id);
        const completedByLabel =
          Number.isInteger(completedByMemberId) && completedByMemberId > 0
            ? this._memberName(memberMap, completedByMemberId)
            : row.completed_by_name || "";
        const completedByName = completedByLabel ? this._escape(completedByLabel) : "";

        const completedByDifferent =
          isDone &&
          Number.isInteger(completedByMemberId) &&
          completedByMemberId > 0 &&
          Number.isInteger(assigneeMemberId) &&
          assigneeMemberId > 0 &&
          completedByMemberId !== assigneeMemberId;

        const displayName = completedByDifferent && completedByName
          ? completedByName
          : assigneeName;

        let irregularNote = "";
        if (completedByDifferent) {
          const completionMode = String(row.completion_mode || "");
          if (completionMode === "takeover") {
            irregularNote = `Took over ${assigneeLabel}'s shift`;
          } else if (row.override_type === "manual_swap") {
            irregularNote = `Swapped from ${originalLabel}`;
          } else {
            irregularNote = `Originally ${assigneeLabel}'s shift`;
          }
        } else if (row.override_type === "manual_swap" && originalLabel && originalLabel !== assigneeLabel) {
          irregularNote = `Originally ${originalLabel}'s shift`;
        } else if (row.override_type === "compensation") {
          irregularNote = this._compensationNote(row, assigneeLabel, originalLabel);
        } else if (isMissed) {
          irregularNote = "Not confirmed";
        }

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
               <span>${isDone ? "Undo" : "Mark done"}</span>
             </button>`);
        } else {
          const futureLabel = isFuture ? "Upcoming" : "Pending";
          const showChip = isDone || isMissed || (!canSwap && row.override_type !== "compensation");
          if (showChip) {
            actionParts.push(`<span class="status-chip ${isDone ? "done" : isMissed ? "missed" : "pending"}">
                 ${isDone ? "Done" : isMissed ? "Missed" : futureLabel}
               </span>`);
          }
        }

        if (canSwap) {
          const hasExistingSwap = row.override_type === "manual_swap";
          const swapLabel = hasExistingSwap ? "Edit swap" : "Swap";
          actionParts.push(`<button
               class="action ${hasExistingSwap ? "swap" : "swap-neutral"}"
               type="button"
               data-action="open-swap-modal"
               data-week-start="${this._escape(row.week_start)}"
               ${isDoneSaving || isSwapSaving ? "disabled" : ""}
             >
               <ha-icon icon="mdi:swap-horizontal"></ha-icon>
               <span>${swapLabel}</span>
             </button>`);
        }

        const canCancelSwap = !isPast && !isDone && isCompensation && !sourceSwapDone;
        if (canCancelSwap) {
          actionParts.push(`<button
               class="action cancel-swap"
               type="button"
               data-action="cancel-linked-swap"
               data-week-start="${this._escape(row.week_start)}"
               ${isDoneSaving || isSwapSaving ? "disabled" : ""}
             >
               <ha-icon icon="mdi:close-circle-outline"></ha-icon>
               <span>Cancel swap</span>
             </button>`);
        }

        const actionControl = actionParts.join("");

        return `
          <li class="week-row ${isCurrent ? "current" : ""} ${isPrevious ? "previous" : ""} ${isPast ? "past" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}"
              data-action="open-history-modal"
              data-week-start="${this._escape(row.week_start)}"
              role="button"
              tabindex="0"
              aria-label="Open shift details for ${this._escape(this._rowDateRange(row))}"
          >
            <div class="week-main">
              <div class="week-top">
                <span class="week-label">${this._escape(this._weekTitle(row, index))}</span>
                <span class="week-dates">${this._escape(this._rowDateRange(row))}</span>
              </div>
              <div class="assignee ${isDone ? "striked" : ""}">
                ${isDone ? '<ha-icon icon="mdi:check"></ha-icon>' : ""}
                <span>${displayName}</span>
              </div>
              ${irregularNote ? `<span class="irregular-note">${this._escape(irregularNote)}</span>` : ""}
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
    const actorMemberId = this._currentMemberId(members);
    const actorName =
      Number.isInteger(actorMemberId) && actorMemberId > 0
        ? this._memberName(memberMap, actorMemberId)
        : String(this._hass?.user?.name || "Someone");
    const actorNameEscaped = this._escape(actorName);
    const currentWeekStartForDistance =
      currentWeek?.week_start ||
      scheduleWeeks[0]?.week_start ||
      weeks[0]?.week_start ||
      "";
    const modalWeek = this._resolveModalWeek(scheduleWeeks);
    const modalAssigneeId = Number(this._modalAssigneeMemberId || modalWeek?.assignee_member_id);
    const modalAssigneeName = this._memberName(memberMap, modalAssigneeId);
    const modalAssigneeNameEscaped = this._escape(modalAssigneeName);
    const modalCleanerId = Number(this._modalCleanerMemberId);
    const hasValidModalCleaner =
      Number.isInteger(modalCleanerId) && modalCleanerId > 0 && modalCleanerId !== modalAssigneeId;
    const modalCleanerName = hasValidModalCleaner
      ? this._memberName(memberMap, modalCleanerId)
      : "the selected flatmate";
    const modalCleanerNameEscaped = this._escape(modalCleanerName);
    const modalWeekLabel = this._formatWeekLabelWithDistance(
      modalWeek,
      0,
      currentWeekStartForDistance
    );
    const modalCompensationWeek =
      this._modalChoice === "takeover" && hasValidModalCleaner
        ? this._findCompensationPreviewWeek(scheduleWeeks, modalCleanerId, modalWeek?.week_start)
        : null;
    const modalCompensationWeekIndex = modalCompensationWeek
      ? scheduleWeeks.findIndex((row) => row.week_start === modalCompensationWeek.week_start)
      : -1;
    const modalCompensationWeekLabel = modalCompensationWeek
      ? this._formatWeekLabelWithDistance(
          modalCompensationWeek,
          modalCompensationWeekIndex >= 0 ? modalCompensationWeekIndex : 0,
          currentWeekStartForDistance
        )
      : "the next regular week (outside loaded schedule)";
    const modalCompensationWeekLabelEscaped = this._escape(modalCompensationWeekLabel);

    const doneEffectsHtml =
      this._modalChoice === "takeover"
        ? `
          <ul class="effect-list">
            <li>Record that <strong>${modalCleanerNameEscaped}</strong> took over <strong>${modalAssigneeNameEscaped}</strong>'s shift in <strong>${this._escape(modalWeekLabel)}</strong>.</li>
            <li>Mark this week as done and credit <strong>${modalCleanerNameEscaped}</strong> as the cleaner.</li>
            <li>Create a one-time return shift: <strong>${modalAssigneeNameEscaped}</strong> is reassigned to <strong>${modalCleanerNameEscaped}</strong>'s next regular week: <strong>${modalCompensationWeekLabelEscaped}</strong>.</li>
          </ul>
          <p class="effect-subtitle">Who will be notified</p>
          <ul class="effect-list notification-list">
            <li><strong>${modalAssigneeNameEscaped}</strong>: "${actorNameEscaped} recorded that ${modalCleanerNameEscaped} took over your shift. Your return shift is ${modalCompensationWeekLabelEscaped}."</li>
            <li><strong>${modalCleanerNameEscaped}</strong>: "${actorNameEscaped} recorded you as the cleaner. ${modalAssigneeNameEscaped} is reassigned to your next regular week ${modalCompensationWeekLabelEscaped}."</li>
          </ul>
        `
        : `
          <ul class="effect-list">
            <li>Mark this shift as done for <strong>${modalAssigneeNameEscaped}</strong>.</li>
            <li>No rotation changes are made; future weeks stay in the same order.</li>
          </ul>
          <p class="effect-subtitle">Who will be notified</p>
          <ul class="effect-list notification-list">
            <li><strong>${modalAssigneeNameEscaped}</strong>: "${actorNameEscaped} confirmed your cleaning shift as done."</li>
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

    const swapModalWeek = this._resolveSwapModalWeek(scheduleWeeks);
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
      ? scheduleWeeks.findIndex((row) => row.week_start === swapModalWeek.week_start)
      : -1;
    const swapWeekLabel = this._formatWeekLabelWithDistance(
      swapModalWeek,
      swapWeekIndex >= 0 ? swapWeekIndex : 0,
      currentWeekStartForDistance
    );
    const swapReturnWeek =
      hasValidSwapTarget && swapModalWeek
        ? this._findSwapReturnPreviewWeek(
            scheduleWeeks,
            swapOriginalAssigneeId,
            swapTargetId,
            swapModalWeek.week_start
          )
        : this._findExistingManualSwapReturnWeek(
            scheduleWeeks,
            swapOriginalAssigneeId,
            swapExistingPartnerId,
            swapModalWeek?.week_start
          );
    const swapReturnWeekLabel = swapReturnWeek
      ? this._formatWeekLabelWithDistance(
          swapReturnWeek,
          Math.max(0, scheduleWeeks.findIndex((row) => row.week_start === swapReturnWeek.week_start)),
          currentWeekStartForDistance
        )
      : "the next regular week (outside loaded schedule)";
    const swapCancelPartnerName =
      Number.isInteger(swapExistingPartnerId) &&
      swapExistingPartnerId > 0 &&
      swapExistingPartnerId !== swapOriginalAssigneeId
        ? this._memberName(memberMap, swapExistingPartnerId)
        : "the swap partner";
    const swapActionWord = swapHasExistingManualSwap ? "updated" : "set";
    const swapEffectsHtml =
      this._swapModalAction === "cancel"
        ? `
          <ul class="effect-list">
            <li>Remove the shift swap pair linked to <strong>${this._escape(swapWeekLabel)}</strong>.</li>
            <li>Restore <strong>${this._escape(swapOriginalAssigneeName)}</strong> for <strong>${this._escape(swapWeekLabel)}</strong> and restore <strong>${this._escape(swapCancelPartnerName)}</strong> for <strong>${this._escape(swapReturnWeekLabel)}</strong>.</li>
            <li>No further weeks are modified.</li>
          </ul>
          <p class="effect-subtitle">Who will be notified</p>
          <ul class="effect-list notification-list">
            <li><strong>${this._escape(swapOriginalAssigneeName)}</strong>: "${actorNameEscaped} canceled the shift swap. You are assigned again for ${this._escape(swapWeekLabel)}."</li>
            <li><strong>${this._escape(swapCancelPartnerName)}</strong>: "${actorNameEscaped} canceled the shift swap. Your regular assignment on ${this._escape(swapReturnWeekLabel)} is restored."</li>
          </ul>
        `
        : `
          <ul class="effect-list">
            <li>Swap the two shifts between <strong>${this._escape(swapWeekLabel)}</strong> and <strong>${this._escape(swapReturnWeekLabel)}</strong>.</li>
            <li><strong>${this._escape(swapTargetName)}</strong> is assigned for <strong>${this._escape(swapWeekLabel)}</strong> instead of <strong>${this._escape(swapOriginalAssigneeName)}</strong>.</li>
            <li><strong>${this._escape(swapOriginalAssigneeName)}</strong> is assigned for <strong>${this._escape(swapReturnWeekLabel)}</strong> instead of <strong>${this._escape(swapTargetName)}</strong>.</li>
            <li>All later weeks keep the normal rotation order.</li>
          </ul>
          <p class="effect-subtitle">Who will be notified</p>
          <ul class="effect-list notification-list">
            <li><strong>${this._escape(swapOriginalAssigneeName)}</strong>: "${actorNameEscaped} ${this._escape(swapActionWord)} the shift swap with ${this._escape(swapTargetName)}. You clean ${this._escape(swapReturnWeekLabel)}."</li>
            <li><strong>${this._escape(swapTargetName)}</strong>: "${actorNameEscaped} ${this._escape(swapActionWord)} the shift swap with ${this._escape(swapOriginalAssigneeName)}. You clean ${this._escape(swapWeekLabel)}."</li>
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
    const historyModalWeek = this._resolveHistoryModalWeek(scheduleWeeks);
    const historyWeekIndex = historyModalWeek
      ? scheduleWeeks.findIndex((row) => row.week_start === historyModalWeek.week_start)
      : -1;
    const historyWeekLabel = this._formatWeekLabelWithDistance(
      historyModalWeek,
      historyWeekIndex >= 0 ? historyWeekIndex : 0,
      currentWeekStartForDistance
    );
    const historyAssigneeId = Number(historyModalWeek?.assignee_member_id);
    const historyAssigneeName = this._memberName(memberMap, historyAssigneeId);
    const historyOriginalId = Number(historyModalWeek?.original_assignee_member_id);
    const historyOriginalName =
      Number.isInteger(historyOriginalId) && historyOriginalId > 0
        ? this._memberName(memberMap, historyOriginalId)
        : "";
    const historyStatus = String(historyModalWeek?.status || "pending");
    const historyCompletionMode = String(historyModalWeek?.completion_mode || "");
    const historyCompletedById = Number(historyModalWeek?.completed_by_member_id);
    const historyCompletedByName =
      Number.isInteger(historyCompletedById) && historyCompletedById > 0
        ? this._memberName(memberMap, historyCompletedById)
        : "";
    const historyOverrideType = historyModalWeek?.override_type || "";
    const historyOverrideSource = historyModalWeek?.override_source || "";
    const historyCompletedAt = historyModalWeek?.completed_at || "";

    const historyStatusLabel =
      historyStatus === "done" ? "Done" : historyStatus === "missed" ? "Missed" : "Pending";
    const historyStatusClass =
      historyStatus === "done" ? "done" : historyStatus === "missed" ? "missed" : "pending";

    let historyContextHtml = "";
    if (historyModalWeek) {
      const ctxParts = [];
      if (historyOverrideType === "manual_swap" && historyOriginalName && historyOriginalName !== historyAssigneeName) {
        const sourceElapsed = this._weekDistanceLabel(
          historyModalWeek?.source_week_start,
          currentWeekStartForDistance
        );
        ctxParts.push(
          `This shift was swapped. Originally ${this._escape(historyOriginalName)}'s turn.`
        );
      } else if (historyOverrideType === "compensation" && historyOverrideSource === "manual") {
        const sourceElapsed = this._weekDistanceLabel(
          historyModalWeek?.source_week_start,
          currentWeekStartForDistance
        );
        const sourceLabel = sourceElapsed ? ` (${sourceElapsed})` : "";
        ctxParts.push(
          `Swap return week. Originally ${this._escape(historyOriginalName || "another flatmate")}'s turn, swapped with ${this._escape(historyAssigneeName)}${sourceLabel}.`
        );
      } else if (historyOverrideType === "compensation") {
        const sourceRange = historyModalWeek?.source_week_start
          ? this._weekDistanceLabel(historyModalWeek.source_week_start, currentWeekStartForDistance)
          : "";
        const sourceLabel = sourceRange ? ` (${sourceRange})` : "";
        ctxParts.push(
          `Return shift. ${this._escape(historyAssigneeName)} is covering for ${this._escape(historyOriginalName || "the original assignee")} after a takeover${sourceLabel}.`
        );
      }

      if (historyStatus === "done") {
        if (historyCompletionMode === "takeover" && historyCompletedByName) {
          ctxParts.push(
            `${this._escape(historyCompletedByName)} took over this shift from ${this._escape(historyAssigneeName)}.`
          );
        } else if (historyCompletedById && historyCompletedById !== historyAssigneeId && historyCompletedByName) {
          const atLabel = historyCompletedAt ? ` on ${this._escape(this._formatEventDateTime(historyCompletedAt))}` : "";
          ctxParts.push(`Completed by ${this._escape(historyCompletedByName)}${atLabel}.`);
        } else {
          const atLabel = historyCompletedAt ? ` on ${this._escape(this._formatEventDateTime(historyCompletedAt))}` : "";
          ctxParts.push(`Completed${atLabel}.`);
        }
      } else if (historyStatus === "missed") {
        ctxParts.push("This shift was not confirmed as done.");
      }

      if (ctxParts.length) {
        historyContextHtml = `<div class="shift-context">${ctxParts.map((p) => `<p class="shift-context-line">${p}</p>`).join("")}</div>`;
      }
    }

    const historyTimeline = Array.isArray(historyModalWeek?.timeline)
      ? historyModalWeek.timeline
      : [];
    const timelineRowsHtml = historyTimeline.length
      ? historyTimeline
          .map((entry) => {
            const isFuture = !!entry.is_future;
            const entryType = String(entry.type || "event");
            const icon = this._escape(entry.icon || "mdi:information");
            const summary = this._escape(entry.summary || "Activity");
            const detail = entry.detail ? this._escape(entry.detail) : "";
            const timestamp = entry.timestamp
              ? this._escape(this._formatEventDateTime(entry.timestamp))
              : "";
            const state = String(entry.state || "").toLowerCase();
            const stateClass = state.replace(/[^a-z0-9_-]/g, "");
            const stateLabel = entry.state_label ? this._escape(entry.state_label) : "";
            const stateBadge =
              entryType === "notification" && stateLabel
                ? `<span class="slot-state ${stateClass}">${stateLabel}</span>`
                : "";

            return `
              <li class="timeline-entry ${isFuture ? "future" : ""} ${entryType}">
                <div class="timeline-icon">
                  <ha-icon icon="${icon}"></ha-icon>
                </div>
                <div class="timeline-content">
                  <div class="timeline-top">
                    <span class="timeline-summary">${summary}</span>
                    ${stateBadge}
                  </div>
                  ${detail ? `<span class="timeline-detail">${detail}</span>` : ""}
                  ${timestamp ? `<span class="timeline-time">${timestamp}</span>` : ""}
                </div>
              </li>
            `;
          })
          .join("")
      : '<li class="empty-list">No activity recorded for this shift.</li>';

    const compactRows = weeks
      .map((row) => {
        const status = String(row?.status || "pending");
        const isDone = status === "done";
        const isMissed = status === "missed";
        const isPreviousNotDone = row.is_previous && !isDone;
        const compactStatusLabel = isDone
          ? "Done"
          : isPreviousNotDone
            ? "Late"
            : isMissed
              ? "Missed"
              : row.is_current
                ? "Pending"
                : "";
        const compactStatusClass = isDone ? "done" : (isMissed || isPreviousNotDone) ? "missed" : "pending";
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
        const completedByLabel =
          Number.isInteger(completedByMemberId) && completedByMemberId > 0
            ? this._memberName(memberMap, completedByMemberId)
            : row.completed_by_name
              ? row.completed_by_name
              : "";
        const completedByName = completedByLabel ? this._escape(completedByLabel) : "";

        const compactCompletedByDifferent =
          isDone &&
          Number.isInteger(completedByMemberId) &&
          completedByMemberId > 0 &&
          Number.isInteger(assigneeMemberId) &&
          assigneeMemberId > 0 &&
          completedByMemberId !== assigneeMemberId;
        const compactDisplayName = compactCompletedByDifferent && completedByName
          ? completedByName
          : assigneeName;

        let compactNote = "";
        if (compactCompletedByDifferent) {
          const compactCompletionMode = String(row.completion_mode || "");
          if (compactCompletionMode === "takeover") {
            compactNote = `Took over ${assigneeName}'s shift`;
          } else if (row.override_type === "manual_swap") {
            compactNote = `Originally ${assigneeName}'s shift (swapped)`;
          } else {
            compactNote = `Originally ${assigneeName}'s shift`;
          }
        } else if (row.override_type === "manual_swap" && originalLabel && originalLabel !== assigneeLabel) {
          compactNote = `Originally ${originalLabel}'s shift`;
        } else if (row.override_type === "compensation") {
          compactNote = this._compensationNote(row, assigneeLabel, originalLabel);
        } else if (isMissed) {
          compactNote = "Not confirmed";
        }

        const leftMarked = row.is_current || (row.is_previous && !isDone);

        return `
          <li class="compact-week-row ${row.is_current ? "current" : ""} ${leftMarked ? "left-marked" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}">
            <div class="compact-left">
              <span class="compact-assignee ${isDone ? "striked" : ""}">${compactDisplayName}</span>
              <span class="compact-week"><span class="compact-date">${compactDateLabel}</span></span>
              ${compactNote ? `<span class="compact-note">${this._escape(compactNote)}</span>` : ""}
            </div>
            <div class="compact-right">
              ${
                compactStatusLabel
                  ? `<span class="compact-status ${compactStatusClass}">${compactStatusLabel}</span>`
                  : ""
              }
              ${compactContext ? `<span class="compact-context">${this._escape(compactContext)}</span>` : ""
              }
            </div>
          </li>
        `;
      })
      .join("");

    const skipCard = compactMode && this._config.eink;

    this._root.innerHTML = `
      ${skipCard ? "" : "<ha-card>"}
        <div class="card ${compactMode ? "compact" : ""} ${this._config.eink ? "eink" : ""}">
          <div class="header ${compactMode ? "compact-header" : ""}">
            <h2>${this._escape(this._config.title)}</h2>
            ${compactMode && this._config.edit_link ? `<a class="edit-badge" href="${this._escape(this._config.edit_link)}"><ha-icon icon="mdi:pencil"></ha-icon> Manage schedule</a>` : ""}
          </div>

          <section>
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

              <p class="modal-week">${this._escape(modalWeekLabel)}</p>
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
                  Use takeover when another flatmate actually cleaned so a return shift is planned automatically.
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
                <h3>${swapHasExistingManualSwap ? "Edit one-time shift swap" : "Create one-time shift swap"}</h3>
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
                  <span>${swapHasExistingManualSwap ? "Update one-time swap" : "Create one-time swap"}</span>
                </label>
                <p class="choice-help">
                  This swaps exactly two weeks: the selected week and the selected flatmate's next regular week.
                </p>
                ${
                  swapHasExistingManualSwap
                    ? `
                      <label class="choice-option">
                        <input type="radio" name="hf-swap-action" value="cancel" ${this._swapModalAction === "cancel" ? "checked" : ""} />
                        <span>Cancel existing swap</span>
                      </label>
                      <p class="choice-help">
                        Restores both swapped weeks to their original assignees and notifies both flatmates.
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

        ${!compactMode && this._historyModalOpen && historyModalWeek ? `
          <div class="modal-backdrop history-modal-backdrop">
            <div class="modal history-modal" role="dialog" aria-modal="true">
              <div class="modal-header">
                <h3>Shift details</h3>
                <button class="icon-btn" type="button" data-action="close-history-modal" aria-label="Close shift details dialog">
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>

              <p class="modal-week">${this._escape(historyWeekLabel)}</p>
              <div class="shift-status-row">
                <span class="shift-assignee-label">Assigned to</span>
                <strong>${this._escape(historyAssigneeName)}</strong>
                <span class="header-status ${historyStatusClass}">${historyStatusLabel}</span>
              </div>

              ${historyContextHtml}

              <div class="timeline-panel">
                <p class="effect-title">Timeline</p>
                <ul class="timeline-list">
                  ${timelineRowsHtml}
                </ul>
              </div>

              <div class="modal-actions">
                <button class="btn secondary" type="button" data-action="close-history-modal">Close</button>
              </div>
            </div>
          </div>
        ` : ""}
      ${skipCard ? "" : "</ha-card>"}

      <style>
        ha-card {
          box-shadow: none;
          border: none;
          background: transparent;
        }

        .card.compact {
          background: transparent;
        }

        .card {
          padding: 0;
          display: grid;
          gap: var(--ha-space-2, 8px);
        }

        .card.compact {
          padding: 0;
          gap: var(--ha-space-2, 8px);
        }

        .header {
          display: flex;
          align-items: center;
          padding: var(--ha-space-1, 4px) var(--ha-space-2, 8px) 0;
        }

        .header h2 {
          margin: 0;
          font-size: var(--ha-font-size-xl, 1.2rem);
          font-weight: var(--ha-font-weight-bold, 700);
          line-height: var(--ha-line-height-condensed, 1.2);
        }

        .compact-header {
          justify-content: space-between;
        }

        .edit-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 2px 10px 2px 6px;
          border-radius: 12px;
          background: var(--secondary-background-color, #f5f5f5);
          color: var(--secondary-text-color);
          font-size: 0.75rem;
          font-weight: 500;
          text-decoration: none;
          cursor: pointer;
          --mdc-icon-size: 14px;
        }

        .edit-badge:hover {
          background: var(--divider-color, #e0e0e0);
          color: var(--primary-text-color);
        }

        .card.compact .header h2 {
          font-size: var(--ha-font-size-l, 1rem);
        }

        .week-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: var(--ha-space-2, 8px);
        }

        .week-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: var(--ha-space-2, 8px);
          align-items: center;
          min-height: 56px;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
          border-radius: var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px));
          box-shadow: var(--ha-card-box-shadow, none);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          cursor: pointer;
          transition: box-shadow var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      border-color var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      background var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .week-row:hover {
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.04);
        }

        .week-row.current:hover {
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.04);
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
          grid-template-columns: 1fr auto;
          gap: 4px 8px;
          align-items: start;
          padding: 8px 10px;
          border-bottom: 1px solid var(--divider-color);
          font-size: 0.83rem;
          line-height: 1.25;
        }

        .compact-week-row:last-child {
          border-bottom: none;
        }

        .compact-week-row.left-marked {
          border-left: 4px solid var(--primary-text-color);
          padding-left: 6px;
        }

        .compact-week-row.current {
          font-weight: 700;
        }

        .compact-left {
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }

        .compact-right {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 2px;
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
          color: var(--secondary-text-color);
          font-style: italic;
          font-size: 0.72rem;
          text-align: right;
        }

        .compact-week-row.current .compact-week {
          color: var(--primary-text-color);
        }

        .compact-assignee {
          font-weight: 700;
          font-size: 0.9rem;
          line-height: 1.2;
        }

        .compact-assignee.striked {
          text-decoration: line-through;
          text-decoration-thickness: 1.5px;
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
          border-left: 4px solid var(--primary-color);
        }

        .week-row.current.done {
          border-left-color: var(--success-color, #43a047);
        }

        .week-row.previous:not(.done) {
          border-left: 4px solid var(--error-color, #d32f2f);
        }

        .week-row.past.done .week-main,
        .week-row.past.done .week-actions .status-chip {
          opacity: 0.35;
        }

        .week-main {
          display: grid;
          min-width: 0;
        }

        .week-row:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: 2px;
        }

        .week-top {
          display: flex;
          align-items: baseline;
          gap: var(--ha-space-2, 8px);
          flex-wrap: wrap;
        }

        .week-label {
          font-weight: var(--ha-font-weight-bold, 700);
          font-size: var(--ha-font-size-m, 0.875rem);
        }

        .week-dates {
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.75rem);
          letter-spacing: 0.4px;
        }

        .assignee {
          margin-top: 2px;
          display: flex;
          align-items: center;
          gap: var(--ha-space-1, 4px);
          font-weight: var(--ha-font-weight-medium, 500);
          min-width: 0;
        }

        .assignee.striked span {
          text-decoration: line-through;
          text-decoration-thickness: 1.5px;
        }

        .irregular-note {
          display: block;
          margin-top: 2px;
          color: var(--warning-color, #f57c00);
          font-size: var(--ha-font-size-xs, 0.75rem);
        }

        .week-actions {
          display: flex;
          flex-direction: column;
          gap: var(--ha-space-1, 4px);
          align-items: stretch;
          position: relative;
          z-index: 1;
        }

        .action,
        .status-chip,
        .btn,
        .icon-btn {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: var(--ha-border-radius-pill, 9999px);
          font: inherit;
          font-size: var(--ha-font-size-s, 0.75rem);
          transition: border-color var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      background var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .action {
          display: inline-flex;
          align-items: center;
          gap: var(--ha-space-1, 4px);
          justify-content: center;
          padding: var(--ha-space-1, 4px) var(--ha-space-2, 8px);
          cursor: pointer;
          min-height: var(--ha-space-7, 28px);
          white-space: nowrap;
          font-weight: var(--ha-font-weight-medium, 500);
        }

        .action.done {
          color: var(--success-color, #43a047);
        }

        .action.undo {
          color: var(--secondary-text-color);
        }

        .action.swap {
          color: var(--primary-color);
        }

        .action.swap-neutral {
          color: var(--secondary-text-color);
        }

        .action.cancel-swap {
          color: var(--primary-color);
        }

        .status-chip {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: var(--ha-space-7, 28px);
          padding: 0 var(--ha-space-2, 8px);
          font-size: var(--ha-font-size-xs, 0.75rem);
          font-weight: var(--ha-font-weight-medium, 500);
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .status-chip.done {
          color: var(--success-color, #43a047);
        }

        .status-chip.missed {
          color: var(--warning-color, #ffa600);
        }

        .action:hover,
        .btn:hover,
        .icon-btn:hover {
          border-color: var(--primary-color);
        }

        .action:disabled,
        .btn:disabled {
          opacity: var(--dark-disabled-opacity, 0.38);
          cursor: default;
        }

        .error {
          border: var(--ha-border-width-sm, 1px) solid rgba(var(--rgb-error-color, 219, 68, 55), 0.4);
          color: var(--error-color, #db4437);
          background: rgba(var(--rgb-error-color, 219, 68, 55), 0.08);
          border-radius: var(--ha-border-radius-md, 8px);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          font-size: var(--ha-font-size-s, 0.75rem);
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
          padding: var(--ha-space-4, 16px);
          box-sizing: border-box;
        }

        .modal {
          width: min(560px, 100%);
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: var(--ha-border-width-sm, 1px) solid var(--divider-color);
          border-radius: var(--ha-border-radius-xl, 16px);
          box-shadow: var(--ha-box-shadow-l, 0 8px 12px rgba(0, 0, 0, 0.14));
          padding: var(--ha-space-4, 16px);
          display: grid;
          gap: var(--ha-space-3, 12px);
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--ha-space-2, 8px);
        }

        .modal-header h3 {
          margin: 0;
          font-size: var(--ha-font-size-l, 1rem);
          font-weight: var(--ha-font-weight-bold, 700);
        }

        .icon-btn {
          cursor: pointer;
          width: var(--ha-space-9, 36px);
          height: var(--ha-space-9, 36px);
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 0;
          border-radius: var(--ha-border-radius-pill, 9999px);
        }

        .modal-week {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.85rem);
        }

        label {
          font-size: var(--ha-font-size-s, 0.85rem);
          color: var(--secondary-text-color);
        }

        select {
          box-sizing: border-box;
          width: 100%;
          min-height: var(--ha-space-10, 40px);
          border-radius: var(--ha-border-radius-lg, 12px);
          border: var(--ha-border-width-sm, 1px) solid var(--input-outlined-idle-border-color, var(--divider-color));
          background: var(--input-fill-color, var(--card-background-color));
          color: var(--input-ink-color, var(--primary-text-color));
          font: inherit;
          font-size: var(--ha-font-size-m, 0.875rem);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          transition: border-color var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        select:hover {
          border-color: var(--input-outlined-hover-border-color, var(--outline-hover-color));
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
          gap: var(--ha-space-1, 4px);
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          border-radius: var(--ha-border-radius-lg, 12px);
          padding: var(--ha-space-3, 12px);
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
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          border-radius: var(--ha-border-radius-lg, 12px);
          padding: var(--ha-space-3, 12px);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.03);
          display: grid;
          gap: var(--ha-space-1, 4px);
        }

        .effect-title {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }

        .effect-subtitle {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
          font-size: 0.78rem;
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

        .notification-list {
          margin-top: -2px;
        }

        .history-panel {
          gap: 8px;
        }

        .history-slot-list,
        .history-event-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 8px;
        }

        .history-slot-row,
        .history-event-row {
          border: 1px solid var(--divider-color);
          border-radius: 10px;
          padding: 8px 10px;
          display: grid;
          gap: 4px;
          background: var(--card-background-color);
        }

        .history-slot-top,
        .history-event-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }

        .history-slot-label,
        .history-event-summary {
          font-weight: 600;
          min-width: 0;
        }

        .slot-state {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 0.72rem;
          text-transform: uppercase;
          letter-spacing: 0.03em;
          white-space: nowrap;
        }

        .slot-state.sent,
        .slot-state.test_redirected,
        .slot-state.not_required {
          color: var(--success-color, #4caf50);
          border-color: color-mix(in srgb, var(--success-color, #4caf50) 45%, var(--divider-color));
        }

        .slot-state.scheduled,
        .slot-state.no_data {
          color: var(--secondary-text-color);
        }

        .slot-state.failed,
        .slot-state.skipped,
        .slot-state.suppressed,
        .slot-state.missing {
          color: var(--warning-color, #f57c00);
          border-color: color-mix(in srgb, var(--warning-color, #f57c00) 45%, var(--divider-color));
        }

        .history-slot-detail,
        .history-slot-time,
        .history-event-action,
        .history-event-reason,
        .history-event-time {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }

        .history-event-action {
          text-transform: uppercase;
          letter-spacing: 0.03em;
          font-size: 0.72rem;
        }

        .history-modal {
          max-height: min(85vh, 680px);
          overflow-y: auto;
        }

        .shift-status-row {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .shift-assignee-label {
          color: var(--secondary-text-color);
          font-size: 0.88rem;
        }

        .shift-status-row strong {
          font-size: 0.95rem;
        }

        .shift-context {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          border-radius: var(--ha-border-radius-lg, 12px);
          padding: var(--ha-space-3, 12px);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.03);
          display: grid;
          gap: var(--ha-space-1, 4px);
        }

        .shift-context-line {
          margin: 0;
          font-size: 0.88rem;
          color: var(--primary-text-color);
          line-height: 1.35;
        }

        .timeline-panel {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          border-radius: var(--ha-border-radius-lg, 12px);
          padding: var(--ha-space-3, 12px);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.03);
          display: grid;
          gap: var(--ha-space-2, 8px);
        }

        .timeline-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 0;
          position: relative;
        }

        .timeline-entry {
          display: grid;
          grid-template-columns: 28px 1fr;
          gap: 8px;
          padding: 6px 0;
          position: relative;
        }

        .timeline-entry:not(:last-child)::before {
          content: "";
          position: absolute;
          left: 13px;
          top: 30px;
          bottom: -6px;
          width: 2px;
          background: var(--divider-color);
        }

        .timeline-entry.future:not(:last-child)::before {
          background: repeating-linear-gradient(
            to bottom,
            var(--divider-color) 0px,
            var(--divider-color) 3px,
            transparent 3px,
            transparent 6px
          );
        }

        .timeline-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          position: relative;
          z-index: 1;
          --mdc-icon-size: 16px;
          color: var(--secondary-text-color);
        }

        .timeline-entry.future .timeline-icon {
          border-style: dashed;
          opacity: 0.7;
        }

        .timeline-entry.future .timeline-content {
          opacity: 0.7;
        }

        .timeline-content {
          display: grid;
          gap: 2px;
          min-width: 0;
          padding-top: 3px;
        }

        .timeline-top {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .timeline-summary {
          font-weight: 600;
          font-size: 0.88rem;
          min-width: 0;
        }

        .timeline-detail {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }

        .timeline-time {
          color: var(--secondary-text-color);
          font-size: 0.76rem;
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
          min-height: var(--ha-space-9, 36px);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          font-weight: var(--ha-font-weight-medium, 500);
        }

        .btn.primary {
          color: var(--primary-color);
          border-color: rgba(var(--rgb-primary-color, 0, 154, 199), 0.4);
          background: rgba(var(--rgb-primary-color, 0, 154, 199), 0.1);
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

          .compact-left {
            gap: 1px;
          }
        }

        .card.eink {
          --divider-color: #000;
          --secondary-text-color: #000;
          --secondary-background-color: #fff;
          --primary-text-color: #000;
          --success-color: #000;
          --warning-color: #000;
          color: #000;
        }

        .card.eink .edit-badge {
          border: 1px solid #000;
        }

        .card.eink .compact-status {
          border-color: #000;
          color: #000;
        }

        .card.eink .compact-week,
        .card.eink .compact-context,
        .card.eink .compact-note {
          font-weight: 400;
        }

        .card.eink .compact-assignee {
          font-weight: 700;
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

    this._bindEvents(scheduleWeeks, members);
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

        ${this._config.layout === "compact" ? `
          <label for="hf-editor-edit-link">Edit link (optional)</label>
          <input id="hf-editor-edit-link" type="text" placeholder="/flatmate/cleaning" value="${this._config.edit_link || ""}" />

          <label>
            <input id="hf-editor-eink" type="checkbox" ${this._config.eink ? "checked" : ""} />
            E-ink display mode (high contrast)
          </label>
        ` : ""}
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
      this._editorReady = false;
      this._emitConfig({
        ...this._config,
        layout: event.target.value || "interactive",
      });
      this._render();
      this._syncEditorValues();
    });

    const editLinkInput = this._root.querySelector("#hf-editor-edit-link");
    editLinkInput?.addEventListener("input", (event) => {
      this._emitConfig({
        ...this._config,
        edit_link: event.target.value || "",
      });
    });

    const einkCheckbox = this._root.querySelector("#hf-editor-eink");
    einkCheckbox?.addEventListener("change", (event) => {
      this._emitConfig({
        ...this._config,
        eink: event.target.checked,
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

    const editLinkInput = this._root.querySelector("#hf-editor-edit-link");
    if (editLinkInput && active !== editLinkInput) {
      editLinkInput.value = this._config.edit_link || "";
    }

    const einkCheckbox = this._root.querySelector("#hf-editor-eink");
    if (einkCheckbox) {
      einkCheckbox.checked = !!this._config.eink;
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
