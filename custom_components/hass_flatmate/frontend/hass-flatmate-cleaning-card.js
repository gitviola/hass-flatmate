class HassFlatmateCleaningCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
    this._errorMessage = "";
    this._pendingDoneWeeks = new Set();
    this._pendingSwapWeeks = new Set();
    this._modalOpen = false;
    this._selectedWeekStart = "";
    this._selectedMemberA = "";
    this._selectedMemberB = "";
  }

  static async getConfigElement() {
    return document.createElement("hass-flatmate-cleaning-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hass_flatmate_cleaning_schedule",
      title: "Cleaning Rotation",
      weeks: 5,
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Cleaning Rotation",
      weeks: 5,
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return 8;
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
      service_swap_week: attrs.service_swap_week || "",
      modal_open: this._modalOpen,
      selected_week: this._selectedWeekStart,
      selected_a: this._selectedMemberA,
      selected_b: this._selectedMemberB,
      pending_done: [...this._pendingDoneWeeks],
      pending_swap: [...this._pendingSwapWeeks],
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
      swapWeek: attributes.service_swap_week || "hass_flatmate_swap_cleaning_week",
    };
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
    if (row?.is_current) {
      return "This week";
    }
    if (index === 1) {
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

  _resolveSelectedWeek(weeks) {
    if (!this._selectedWeekStart) {
      return null;
    }
    return weeks.find((row) => row.week_start === this._selectedWeekStart) || null;
  }

  _openSwapModal(weekRow, members) {
    if (!weekRow || !weekRow.week_start) {
      return;
    }

    const memberIds = members.map((m) => Number(m.member_id)).filter((id) => Number.isInteger(id) && id > 0);
    const baselineId = Number(weekRow.baseline_assignee_member_id);
    const effectiveId = Number(weekRow.assignee_member_id);

    let memberA = Number.isInteger(baselineId) && baselineId > 0 ? baselineId : memberIds[0];
    let memberB = Number.isInteger(effectiveId) && effectiveId > 0 && effectiveId !== memberA
      ? effectiveId
      : memberIds.find((id) => id !== memberA);

    if (!Number.isInteger(memberA) || !Number.isInteger(memberB)) {
      this._errorMessage = "Need at least two flatmates to create a swap.";
      this._render();
      return;
    }

    this._selectedWeekStart = weekRow.week_start;
    this._selectedMemberA = String(memberA);
    this._selectedMemberB = String(memberB);
    this._modalOpen = true;
    this._errorMessage = "";
    this._render();
  }

  _closeSwapModal() {
    this._modalOpen = false;
    this._selectedWeekStart = "";
    this._selectedMemberA = "";
    this._selectedMemberB = "";
    this._render();
  }

  async _callService(service, data) {
    if (!this._hass || !this._stateObj) {
      return;
    }
    const meta = this._serviceMeta(this._stateObj.attributes || {});
    await this._hass.callService(meta.domain, service, data);
  }

  async _markDone(weekStart) {
    if (!weekStart || this._pendingDoneWeeks.has(weekStart)) {
      return;
    }

    this._pendingDoneWeeks.add(weekStart);
    this._errorMessage = "";
    this._render();

    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.markDone, { week_start: weekStart });
    } catch (error) {
      this._pendingDoneWeeks.delete(weekStart);
      this._errorMessage = error?.message || "Unable to mark cleaning as done";
      this._render();
    }
  }

  async _applySwap(cancel) {
    const weekStart = this._selectedWeekStart;
    const memberA = Number(this._selectedMemberA);
    const memberB = Number(this._selectedMemberB);
    const members = Array.isArray(this._stateObj?.attributes?.members)
      ? this._stateObj.attributes.members
      : [];
    const memberIds = members
      .map((member) => Number(member?.member_id))
      .filter((id) => Number.isInteger(id) && id > 0);
    const safeMemberA = Number.isInteger(memberA) && memberA > 0 ? memberA : memberIds[0];
    const safeMemberB = Number.isInteger(memberB) && memberB > 0 && memberB !== safeMemberA
      ? memberB
      : memberIds.find((id) => id !== safeMemberA);

    if (!weekStart) {
      return;
    }
    if (!Number.isInteger(safeMemberA) || !Number.isInteger(safeMemberB)) {
      this._errorMessage = "Need at least two flatmates to create or cancel a swap.";
      this._render();
      return;
    }
    if (!cancel && safeMemberA === safeMemberB) {
      this._errorMessage = "Please select two different flatmates for the swap.";
      this._render();
      return;
    }

    if (this._pendingSwapWeeks.has(weekStart)) {
      return;
    }

    this._pendingSwapWeeks.add(weekStart);
    this._errorMessage = "";
    this._render();

    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.swapWeek, {
        week_start: weekStart,
        member_a_id: safeMemberA,
        member_b_id: safeMemberB,
        cancel,
      });
      this._pendingSwapWeeks.delete(weekStart);
      this._closeSwapModal();
    } catch (error) {
      this._pendingSwapWeeks.delete(weekStart);
      this._errorMessage = error?.message || "Unable to update swap";
      this._render();
    }
  }

  _bindEvents(weeks, members) {
    this._root.querySelectorAll("[data-action='mark-done']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._markDone(el.dataset.weekStart || "");
      });
    });

    this._root.querySelectorAll("[data-action='open-swap']").forEach((el) => {
      el.addEventListener("click", () => {
        const weekStart = el.dataset.weekStart || "";
        const row = weeks.find((item) => item.week_start === weekStart);
        this._openSwapModal(row, members);
      });
    });

    const memberASelect = this._root.querySelector("#hf-swap-member-a");
    const memberBSelect = this._root.querySelector("#hf-swap-member-b");

    memberASelect?.addEventListener("change", (event) => {
      this._selectedMemberA = event.target.value;
      this._render();
    });
    memberBSelect?.addEventListener("change", (event) => {
      this._selectedMemberB = event.target.value;
      this._render();
    });

    this._root.querySelector("[data-action='close-swap']")?.addEventListener("click", () => {
      this._closeSwapModal();
    });

    this._root.querySelector("[data-action='apply-swap']")?.addEventListener("click", async () => {
      await this._applySwap(false);
    });

    this._root.querySelector("[data-action='cancel-swap']")?.addEventListener("click", async () => {
      await this._applySwap(true);
    });

    this._root.querySelector(".modal-backdrop")?.addEventListener("click", (event) => {
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

    const activeWeekStarts = new Set(rawWeeks.map((row) => row.week_start));
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

    const weeksToShow = this._coerceWeeks(this._config.weeks);
    const weeks = rawWeeks
      .slice()
      .sort((a, b) => String(a.week_start || "").localeCompare(String(b.week_start || "")))
      .slice(0, weeksToShow);

    for (const row of weeks) {
      if (String(row?.status || "") === "done") {
        this._pendingDoneWeeks.delete(String(row.week_start || ""));
      }
    }

    const currentWeek = weeks.find((row) => row.is_current) || weeks[0] || null;
    const currentStatus = String(currentWeek?.status || "pending");

    const statusLabel = currentStatus === "done"
      ? "Done"
      : currentStatus === "missed"
        ? "Missed"
        : "Pending";

    const currentAssigneeName = currentWeek?.assignee_name || (currentWeek?.assignee_member_id ? `Member ${currentWeek.assignee_member_id}` : "Unassigned");
    const selectedWeek = this._resolveSelectedWeek(weeks);

    const weekRows = weeks
      .map((row, index) => {
        const status = String(row?.status || "pending");
        const isDone = status === "done" || this._pendingDoneWeeks.has(row.week_start);
        const isMissed = status === "missed";
        const isPending = !isDone && !isMissed;
        const isCurrent = !!row.is_current;
        const isSwapPending = this._pendingSwapWeeks.has(row.week_start);

        const assigneeName = this._escape(
          row.assignee_name || (row.assignee_member_id ? `Member ${row.assignee_member_id}` : "Unassigned")
        );
        const baselineName = row.baseline_assignee_name
          ? this._escape(row.baseline_assignee_name)
          : (row.baseline_assignee_member_id ? `Member ${row.baseline_assignee_member_id}` : "");
        const completedByName = row.completed_by_name
          ? this._escape(row.completed_by_name)
          : (row.completed_by_member_id ? `Member ${row.completed_by_member_id}` : "");

        let doneMeta = "";
        if (isDone && completedByName) {
          doneMeta = `<span class="meta-note">Done by ${completedByName}</span>`;
        } else if (isMissed) {
          doneMeta = '<span class="meta-note missed">Not confirmed</span>';
        }

        const overrideBadge = row.override_type
          ? `<span class="badge">${this._escape(row.override_type === "manual_swap" ? "Swap" : "Compensation")}</span>`
          : "";

        const secondary = row.override_type === "manual_swap" && baselineName && baselineName !== assigneeName
          ? `<span class="meta-note">Baseline: ${baselineName}</span>`
          : "";

        const doneButton = isCurrent && !isDone
          ? `<button class="action done" type="button" data-action="mark-done" data-week-start="${this._escape(row.week_start)}" ${this._pendingDoneWeeks.has(row.week_start) ? "disabled" : ""}>
               <ha-icon icon="mdi:check-circle-outline"></ha-icon>
               <span>${this._pendingDoneWeeks.has(row.week_start) ? "Saving..." : "Mark done"}</span>
             </button>`
          : `<span class="status-chip ${isDone ? "done" : isMissed ? "missed" : "pending"}">
               ${isDone ? "Done" : isMissed ? "Missed" : "Pending"}
             </span>`;

        return `
          <li class="week-row ${isCurrent ? "current" : ""} ${isDone ? "done" : ""} ${isMissed ? "missed" : ""}">
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
              ${doneButton}
              <button class="action swap" type="button" data-action="open-swap" data-week-start="${this._escape(row.week_start)}" ${isSwapPending ? "disabled" : ""}>
                <ha-icon icon="mdi:swap-horizontal"></ha-icon>
                <span>${row.override_type === "manual_swap" ? "Edit swap" : "Swap"}</span>
              </button>
            </div>
          </li>
        `;
      })
      .join("");

    const selectedWeekRange = selectedWeek ? this._rowDateRange(selectedWeek) : "";
    const selectedWeekTitle = selectedWeek ? this._weekTitle(selectedWeek, 0) : "";
    const hasManualSwap = selectedWeek?.override_type === "manual_swap";

    const memberOptions = members
      .map((member) => {
        const id = Number(member.member_id);
        const name = this._escape(member.name || `Member ${id}`);
        if (!Number.isInteger(id) || id <= 0) {
          return "";
        }
        return `<option value="${id}">${name}</option>`;
      })
      .join("");

    const selectedAName = memberMap.get(Number(this._selectedMemberA)) || "member A";
    const selectedBName = memberMap.get(Number(this._selectedMemberB)) || "member B";

    const errorMessage = this._errorMessage ? this._escape(this._errorMessage) : "";

    this._root.innerHTML = `
      <ha-card>
        <div class="card">
          <div class="header">
            <div>
              <h2>${this._escape(this._config.title)}</h2>
              <p>${this._escape(currentAssigneeName)} • ${statusLabel}</p>
            </div>
            <span class="header-status ${currentStatus}">${statusLabel}</span>
          </div>

          <section>
            <h3>Upcoming schedule</h3>
            <ul class="week-list">
              ${weekRows || '<li class="empty-list">No schedule data yet</li>'}
            </ul>
          </section>

          ${errorMessage ? `<div class="error">${errorMessage}</div>` : ""}
        </div>

        ${this._modalOpen && selectedWeek ? `
          <div class="modal-backdrop">
            <div class="modal" role="dialog" aria-modal="true">
              <div class="modal-header">
                <h3>Schedule override</h3>
                <button class="icon-btn" type="button" data-action="close-swap" aria-label="Close swap editor">
                  <ha-icon icon="mdi:close"></ha-icon>
                </button>
              </div>

              <p class="modal-week">${this._escape(selectedWeekTitle)} • ${this._escape(selectedWeekRange)}</p>

              <label for="hf-swap-member-a">Flatmate A</label>
              <select id="hf-swap-member-a">
                ${memberOptions}
              </select>

              <label for="hf-swap-member-b">Flatmate B</label>
              <select id="hf-swap-member-b">
                ${memberOptions}
              </select>

              <p class="modal-preview">
                Preview: <strong>${this._escape(selectedAName)}</strong> and <strong>${this._escape(selectedBName)}</strong>
                will swap this week.
              </p>

              <div class="modal-actions">
                <button class="btn secondary" type="button" data-action="close-swap">Close</button>
                ${hasManualSwap ? '<button class="btn warn" type="button" data-action="cancel-swap">Cancel existing swap</button>' : ''}
                <button class="btn primary" type="button" data-action="apply-swap">Save swap</button>
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

        .header p {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }

        .header-status {
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 0.78rem;
          border: 1px solid var(--divider-color);
          text-transform: uppercase;
          letter-spacing: 0.03em;
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

        .week-row.current {
          border-color: color-mix(in srgb, var(--primary-color) 45%, var(--divider-color));
          background: color-mix(in srgb, var(--primary-color) 8%, var(--card-background-color));
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

        .action.swap {
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

        .btn.warn {
          color: var(--warning-color, #f57c00);
          border-color: color-mix(in srgb, var(--warning-color, #f57c00) 35%, var(--divider-color));
          background: color-mix(in srgb, var(--warning-color, #f57c00) 10%, var(--card-background-color));
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
        }
      </style>
    `;

    const selectA = this._root.querySelector("#hf-swap-member-a");
    const selectB = this._root.querySelector("#hf-swap-member-b");
    if (selectA && this._selectedMemberA) {
      selectA.value = this._selectedMemberA;
    }
    if (selectB && this._selectedMemberB) {
      selectB.value = this._selectedMemberB;
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
    description: "Cleaning schedule with week status, mark-done flow, and swap overrides.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#cleaning-ui-card",
  });
}
