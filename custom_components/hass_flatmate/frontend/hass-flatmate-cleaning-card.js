class HassFlatmateCleaningCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
    this._errorMessage = "";
    this._pendingDoneWeeks = new Set();
    this._modalOpen = false;
    this._modalWeekStart = "";
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = "";
    this._modalCleanerMemberId = "";
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
      layout: this._layout(),
      modal_open: this._modalOpen,
      modal_week_start: this._modalWeekStart,
      modal_choice: this._modalChoice,
      modal_assignee_member_id: this._modalAssigneeMemberId,
      modal_cleaner_member_id: this._modalCleanerMemberId,
      pending_done: [...this._pendingDoneWeeks],
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

  _closeDoneModal() {
    this._modalOpen = false;
    this._modalWeekStart = "";
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = "";
    this._modalCleanerMemberId = "";
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
    this._modalWeekStart = weekRow.week_start;
    this._modalChoice = "confirm_assignee";
    this._modalAssigneeMemberId = String(assigneeMemberId);
    this._modalCleanerMemberId = defaultCleaner ? String(defaultCleaner) : "";
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

  async _runWeekAction(weekStart, action, fallbackError) {
    if (!weekStart || this._pendingDoneWeeks.has(weekStart)) {
      return false;
    }

    this._pendingDoneWeeks.add(weekStart);
    this._errorMessage = "";
    this._render();

    let ok = false;
    try {
      await action();
      await this._requestEntityRefresh();
      ok = true;
    } catch (error) {
      this._errorMessage = error?.message || fallbackError;
      this._render();
    } finally {
      this._pendingDoneWeeks.delete(weekStart);
      this._render();
    }

    return ok;
  }

  async _markDone(weekStart, completedByMemberId = null) {
    const payload = completedByMemberId
      ? { week_start: weekStart, completed_by_member_id: completedByMemberId }
      : { week_start: weekStart };
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    return this._runWeekAction(
      weekStart,
      async () => {
        await this._callService(meta.markDone, payload);
      },
      "Unable to mark cleaning as done"
    );
  }

  async _markUndone(weekStart) {
    const meta = this._serviceMeta(this._stateObj?.attributes || {});
    return this._runWeekAction(
      weekStart,
      async () => {
        await this._callService(meta.markUndone, { week_start: weekStart });
      },
      "Unable to mark cleaning as undone"
    );
  }

  async _markTakeoverDone(weekStart, originalAssigneeMemberId, cleanerMemberId) {
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
      "Unable to record takeover completion"
    );
  }

  async _toggleDone(row, members) {
    if (!row || !row.week_start) {
      return;
    }
    const weekStart = String(row.week_start);
    const status = String(row.status || "pending");
    if (status === "done") {
      await this._markUndone(weekStart);
      return;
    }

    if (this._isNonAssignee(row, members)) {
      this._openDoneModal(row, members);
      return;
    }

    await this._markDone(weekStart);
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
      ok = await this._markTakeoverDone(String(row.week_start), assigneeMemberId, cleanerMemberId);
    } else {
      ok = await this._markDone(String(row.week_start), assigneeMemberId);
    }

    if (ok) {
      this._closeDoneModal();
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

    this._root.querySelector(".modal-backdrop")?.addEventListener("click", (event) => {
      if (event.target?.classList?.contains("modal-backdrop")) {
        this._closeDoneModal();
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

    const weeksToShow = this._coerceWeeks(this._config.weeks);
    const weeks = rawWeeks
      .slice()
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
        const canToggle = isCurrent || isPrevious;
        const isSaving = this._pendingDoneWeeks.has(String(row.week_start || ""));

        const assigneeName = this._escape(
          row.assignee_name || (row.assignee_member_id ? `Member ${row.assignee_member_id}` : "Unassigned")
        );
        const originalName = row.original_assignee_name
          ? this._escape(row.original_assignee_name)
          : row.original_assignee_member_id
            ? `Member ${row.original_assignee_member_id}`
            : "";
        const completedByName = row.completed_by_name
          ? this._escape(row.completed_by_name)
          : row.completed_by_member_id
            ? `Member ${row.completed_by_member_id}`
            : "";

        let doneMeta = "";
        if (isDone && completedByName) {
          doneMeta = `<span class="meta-note">Done by ${completedByName}</span>`;
        } else if (isMissed) {
          doneMeta = '<span class="meta-note missed">Not confirmed</span>';
        }

        const overrideBadge = row.override_type
          ? `<span class="badge">${this._escape(row.override_type === "manual_swap" ? "Swap" : "Compensation")}</span>`
          : "";

        const secondary =
          row.override_type === "manual_swap" && originalName && originalName !== assigneeName
            ? `<span class="meta-note">Original: ${originalName}</span>`
            : row.override_type === "compensation"
              ? '<span class="meta-note">Compensation override</span>'
              : "";

        const actionControl = canToggle
          ? `<button
               class="action ${isDone ? "undo" : "done"}"
               type="button"
               data-action="toggle-done"
               data-week-start="${this._escape(row.week_start)}"
               ${isSaving ? "disabled" : ""}
             >
               <ha-icon icon="${isDone ? "mdi:undo-variant" : "mdi:check-circle-outline"}"></ha-icon>
               <span>${isSaving ? "Saving..." : isDone ? "Undo" : "Mark done"}</span>
             </button>`
          : `<span class="status-chip ${isDone ? "done" : isMissed ? "missed" : "pending"}">
               ${isDone ? "Done" : isMissed ? "Missed" : "Pending"}
             </span>`;

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
    const modalAssigneeName =
      memberMap.get(modalAssigneeId) ||
      (Number.isInteger(modalAssigneeId) && modalAssigneeId > 0 ? `Member ${modalAssigneeId}` : "Unknown");

    const cleanerOptions = members
      .map((member) => {
        const memberId = Number(member?.member_id);
        if (!Number.isInteger(memberId) || memberId <= 0 || memberId === modalAssigneeId) {
          return "";
        }
        const name = this._escape(member?.name || `Member ${memberId}`);
        return `<option value="${memberId}">${name}</option>`;
      })
      .join("");

    const compactRows = weeks
      .map((row, index) => {
        const status = String(row?.status || "pending");
        const isDone = status === "done";
        const isMissed = status === "missed";
        const isFuture = !row.is_current && !row.is_previous && !row.is_past;
        const compactStatusLabel = isDone ? "Done" : isMissed ? "Missed" : isFuture ? "Upcoming" : "Pending";
        const compactStatusClass = isDone ? "done" : isMissed ? "missed" : isFuture ? "upcoming" : "pending";

        const assigneeName = this._escape(
          row.assignee_name || (row.assignee_member_id ? `Member ${row.assignee_member_id}` : "Unassigned")
        );
        const originalName = row.original_assignee_name
          ? this._escape(row.original_assignee_name)
          : row.original_assignee_member_id
            ? `Member ${row.original_assignee_member_id}`
            : "";

        let compactNote = "";
        if (row.override_type === "manual_swap" && originalName && originalName !== assigneeName) {
          compactNote = `Swap (original: ${originalName})`;
        } else if (row.override_type === "compensation") {
          compactNote = "Compensation week";
        } else if (isDone && row.completed_by_name) {
          compactNote = `Done by ${this._escape(row.completed_by_name)}`;
        } else if (isMissed) {
          compactNote = "Not confirmed";
        }

        return `
          <li class="compact-week-row ${row.is_current ? "current" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}">
            <div class="compact-top">
              <span class="compact-week">${this._escape(this._weekTitle(row, index))} • ${this._escape(this._rowDateRange(row))}</span>
              <span class="compact-status ${compactStatusClass}">${compactStatusLabel}</span>
            </div>
            <span class="compact-assignee">${assigneeName}</span>
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
          <div class="modal-backdrop">
            <div class="modal" role="dialog" aria-modal="true">
              <div class="modal-header">
                <h3>Confirm cleaning completion</h3>
                <button class="icon-btn" type="button" data-action="close-done-modal" aria-label="Close confirmation dialog">
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>

              <p class="modal-week">${this._escape(this._weekTitle(modalWeek, 0))} • ${this._escape(this._rowDateRange(modalWeek))}</p>
              <p class="modal-preview">Assigned flatmate: <strong>${this._escape(modalAssigneeName)}</strong></p>

              <div class="choice-group">
                <label class="choice-option">
                  <input type="radio" name="hf-modal-choice" value="confirm_assignee" ${this._modalChoice !== "takeover" ? "checked" : ""} />
                  <span>${this._escape(modalAssigneeName)} cleaned, I am only confirming it.</span>
                </label>
                <p class="choice-help">
                  Marks this week as done for ${this._escape(modalAssigneeName)} and notifies them that you confirmed it.
                </p>

                <label class="choice-option">
                  <input type="radio" name="hf-modal-choice" value="takeover" ${this._modalChoice === "takeover" ? "checked" : ""} />
                  <span>Someone else took over this shift.</span>
                </label>
                <p class="choice-help">
                  Records a takeover and automatically schedules compensation. Both involved flatmates are notified.
                </p>
              </div>

              ${
                this._modalChoice === "takeover"
                  ? `
                    <label for="hf-modal-cleaner">Who cleaned</label>
                    <select id="hf-modal-cleaner">
                      ${cleanerOptions}
                    </select>
                  `
                  : ""
              }

              <div class="modal-actions">
                <button class="btn secondary" type="button" data-action="close-done-modal">Close</button>
                <button class="btn primary" type="button" data-action="submit-done-modal">
                  ${this._modalChoice === "takeover" ? "Record takeover" : "Confirm done"}
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
          font-weight: 600;
        }

        .compact-week-row.done .compact-assignee {
          text-decoration: line-through;
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

        .compact-assignee {
          font-weight: 600;
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

        .compact-status.upcoming {
          color: var(--secondary-text-color);
        }

        .compact-note {
          color: var(--secondary-text-color);
          font-size: 0.78rem;
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

    this._bindEvents(weeks, members);
  }
}

class HassFlatmateCleaningCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
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
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
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
      entityPicker.hass = this._hass;
      entityPicker.value = this._config.entity || "sensor.hass_flatmate_cleaning_schedule";
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
