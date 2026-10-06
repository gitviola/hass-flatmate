class HassFlatmateDistributionCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
    this._history = null;
    this._historyRequestId = 0;
  }

  static async getConfigElement() {
    return document.createElement("hass-flatmate-distribution-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hass_flatmate_shopping_distribution_90d",
      title: "Shopping Distribution",
      layout: "bars",
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Shopping Distribution",
      layout: "bars",
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return this._layout() === "compact" ? 3 : 6;
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
      total_completed: attrs.total_completed,
      unknown_excluded_count: attrs.unknown_excluded_count,
      window_days: attrs.window_days,
      distribution: attrs.distribution,
      layout: this._layout(),
      next: this._nextBuyers(hass),
      next_note: this._nextBuyerNote(hass),
      labels: this._recommendations(hass),
    });
  }

  _nextBuyers(hass = this._hass) {
    if (this._config?.show_next_buyer === false) {
      return [];
    }
    const entityId = this._config?.next_buyer_entity || "sensor.hass_flatmate_shopping_next_buyer";
    const recommended = hass?.states?.[entityId]?.attributes?.recommended;
    if (!Array.isArray(recommended)) {
      return [];
    }
    return recommended.map((row, idx) => ({
      memberId: Number(row?.member_id),
      primary: idx === 0,
    }));
  }

  // Per-flatmate label ("Buy next", "Catch up", "Just moved in", "Thanks!"); e-ink keeps the plain highlight.
  _recommendations(hass = this._hass) {
    if (this._config?.show_next_buyer === false || this._config?.eink) {
      return {};
    }
    const entityId = this._config?.next_buyer_entity || "sensor.hass_flatmate_shopping_next_buyer";
    const order = hass?.states?.[entityId]?.attributes?.order;
    if (!Array.isArray(order)) {
      return {};
    }
    return Object.fromEntries(order.map((row) => [Number(row?.member_id), String(row?.recommendation || "")]));
  }

  _nextBuyerNote(hass = this._hass) {
    if (this._config?.show_next_buyer === false) {
      return "";
    }
    const entityId = this._config?.next_buyer_entity || "sensor.hass_flatmate_shopping_next_buyer";
    return String(hass?.states?.[entityId]?.attributes?.note || "");
  }

  _layout() {
    const raw = String(this._config?.layout || "bars").toLowerCase();
    return raw === "compact" ? "compact" : "bars";
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _nameHtml(row, className) {
    const memberId = Number(row.memberId);
    if (!this._historyEnabled() || !Number.isInteger(memberId) || memberId <= 0) {
      return `<span class="${className}">${this._escape(row.name)}</span>`;
    }
    return `<button class="${className} name-btn" type="button" data-history-member="${memberId}" data-history-name="${this._escape(row.name)}" title="Show purchase history">${this._escape(row.name)}</button>`;
  }

  _number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  _historyEnabled() {
    return !this._config?.eink;
  }

  async _openHistory(memberId, name) {
    if (!this._historyEnabled() || !Number.isInteger(memberId) || memberId <= 0 || !this._hass) {
      return;
    }
    const requestId = ++this._historyRequestId;
    this._history = { memberId, name, loading: true, error: "", data: null };
    this._render();

    try {
      const result = await this._hass.callWS({
        type: "call_service",
        domain: "hass_flatmate",
        service: "hass_flatmate_get_member_purchases",
        service_data: { member_id: memberId },
        return_response: true,
      });
      if (requestId !== this._historyRequestId || !this._history) {
        return;
      }
      this._history = { ...this._history, loading: false, data: result?.response || {} };
    } catch (error) {
      if (requestId !== this._historyRequestId || !this._history) {
        return;
      }
      this._history = {
        ...this._history,
        loading: false,
        error: error?.message || "Could not load the purchase history.",
      };
    }
    this._render();
  }

  _closeHistory() {
    this._historyRequestId += 1;
    this._history = null;
    this._render();
  }

  _formatPurchaseDate(value) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "";
    }
    const locale = this._hass?.locale?.language || this._hass?.language || undefined;
    return parsed.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
  }

  _historyModalHtml(windowDays) {
    const history = this._history;
    if (!history) {
      return "";
    }

    const data = history.data || {};
    const purchases = Array.isArray(data.purchases) ? data.purchases : [];
    const days = Math.max(1, Math.round(this._number(data.window_days, windowDays)));
    const inWindow = purchases.filter((row) => row?.in_window);
    const older = purchases.filter((row) => !row?.in_window);

    const rowHtml = (row) => `
      <li class="purchase-row">
        <span class="purchase-name">${this._escape(row?.name || "Item")}</span>
        <span class="purchase-date">${this._escape(this._formatPurchaseDate(row?.completed_at))}</span>
      </li>
    `;
    const sectionHtml = (title, hint, rows, extraClass) => `
      <section class="purchase-section ${extraClass}">
        <div class="purchase-section-head">
          <span class="purchase-section-title">${title}</span>
          <span class="purchase-section-hint">${hint}</span>
        </div>
        ${rows.length
          ? `<ul class="purchase-list">${rows.map(rowHtml).join("")}</ul>`
          : '<p class="empty">Nothing in this period.</p>'}
      </section>
    `;

    let bodyHtml;
    if (history.loading) {
      bodyHtml = '<p class="empty">Loading purchase history…</p>';
    } else if (history.error) {
      bodyHtml = `<p class="history-error">${this._escape(history.error)}</p>`;
    } else if (purchases.length === 0) {
      bodyHtml = '<p class="empty">No purchases recorded yet.</p>';
    } else {
      bodyHtml = `
        <p class="history-summary">
          <strong>${inWindow.length}</strong> in the last ${days} days &middot; <strong>${purchases.length}</strong> in total
        </p>
        <div class="history-scroll">
          ${sectionHtml(`Last ${days} days`, "counted in the distribution", inWindow, "in-window")}
          ${older.length
            ? sectionHtml(`Older than ${days} days`, "not counted", older, "outside-window")
            : ""}
        </div>
      `;
    }

    return `
      <div class="modal-backdrop" data-history-backdrop>
        <div class="modal" role="dialog" aria-modal="true" aria-label="Purchase history">
          <div class="modal-header">
            <h3>${this._escape(data.display_name || history.name)}'s purchases</h3>
            <button class="icon-btn" type="button" data-history-close aria-label="Close purchase history">
              <ha-icon icon="mdi:close"></ha-icon>
            </button>
          </div>
          ${bodyHtml}
        </div>
      </div>
    `;
  }

  _bindEvents() {
    this._root.querySelectorAll("[data-history-member]").forEach((el) => {
      el.addEventListener("click", () => {
        this._openHistory(Number(el.dataset.historyMember), el.dataset.historyName || "");
      });
    });
    this._root.querySelectorAll("[data-history-close]").forEach((el) => {
      el.addEventListener("click", () => this._closeHistory());
    });
    this._root.querySelector("[data-history-backdrop]")?.addEventListener("click", (event) => {
      if (event.target?.hasAttribute?.("data-history-backdrop")) {
        this._closeHistory();
      }
    });
  }

  _render() {
    if (!this._config || !this._hass || !this._root) {
      return;
    }

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this._root.innerHTML = `
        <ha-card>
          <div class="empty">Entity not found: <code>${this._escape(this._config.entity)}</code></div>
        </ha-card>
      `;
      return;
    }

    const attrs = stateObj.attributes || {};
    const rawDistribution = Array.isArray(attrs.distribution) ? attrs.distribution : [];
    const distribution = rawDistribution.map((row) => {
      const name = String(row?.name || "Unknown");
      const count = Math.max(0, Math.round(this._number(row?.count, 0)));
      const memberId = row?.member_id;
      return { name, count, memberId };
    });

    const totalCompleted = Math.max(
      0,
      Math.round(this._number(attrs.total_completed, this._number(stateObj.state, 0)))
    );
    const unknownExcluded = Math.max(
      0,
      Math.round(this._number(attrs.unknown_excluded_count, 0))
    );
    const windowDays = Math.max(1, Math.round(this._number(attrs.window_days, 90)));

    const maxCount = Math.max(
      1,
      ...distribution.map((row) => row.count)
    );

    const palette = [
      "#1f7a8c",
      "#2c7da0",
      "#2a9d8f",
      "#4d908e",
      "#577590",
      "#43aa8b",
      "#7aa95c",
      "#bc6c25",
    ];

    const nextBuyers = this._nextBuyers();
    const nextFor = (row) => nextBuyers.find((buyer) => buyer.memberId === Number(row.memberId)) || null;
    const recommendations = this._recommendations();
    const chipFor = (row) => {
      const next = nextFor(row);
      const label = this._config.eink ? (next ? "Should buy" : "") : recommendations[Number(row.memberId)] || "";
      if (!label) {
        return "";
      }
      let variant = "quiet";
      if (next) {
        variant = next.primary ? "" : "then";
      } else if (label === "Catch up") {
        variant = "catch-up";
      }
      return `<span class="next-chip ${variant}">${this._escape(label)}</span>`;
    };

    const rowsHtml = distribution
      .map((row, idx) => {
        const relativeWidth = maxCount > 0 ? (row.count / maxCount) * 100 : 0;
        const barWidth = row.count > 0
          ? Math.max(6, Math.min(100, relativeWidth))
          : 0;
        const accent = palette[idx % palette.length];
        const next = nextFor(row);

        return `
          <li class="row ${next ? "next" : ""}" style="--accent:${accent}; --bar-width:${barWidth}%;">
            <div class="row-head">
              <span class="name-wrap">
                ${this._nameHtml(row, "name")}
                ${chipFor(row)}
              </span>
              <span class="metrics">${row.count} purchase${row.count === 1 ? "" : "s"}</span>
            </div>
            <div class="track">
              <div class="fill"></div>
            </div>
          </li>
        `;
      })
      .join("");

    const emptyState = distribution.length === 0
      ? '<li class="empty-list">No flatmates synced yet.</li>'
      : "";

    const unknownBadge = unknownExcluded > 0
      ? `<span class="chip">Unknown excluded: ${unknownExcluded}</span>`
      : "";
    const metaRowHtml = unknownBadge
      ? `<div class="meta-row">${unknownBadge}</div>`
      : "";

    const compactShares = (() => {
      const memberCount = distribution.length;
      if (memberCount === 0) {
        return [];
      }
      const minShare = Math.max(4, Math.min(10, 36 / memberCount));
      const rawShares = distribution.map((item) => {
        if (totalCompleted <= 0) {
          return 100 / memberCount;
        }
        return (item.count / totalCompleted) * 100;
      });
      const flooredShares = rawShares.map((share) => Math.max(minShare, share));
      const flooredTotal = flooredShares.reduce((sum, share) => sum + share, 0) || 1;
      return flooredShares.map((share) => (share / flooredTotal) * 100);
    })();

    const compactRowsHtml = distribution
      .map((row, idx) => {
        const next = nextFor(row);
        const label = recommendations[Number(row.memberId)] || "";
        return `
          <li class="compact-cell ${next ? (next.primary ? "next" : "next then") : ""}" style="--compact-share:${compactShares[idx] || 0};">
            ${this._nameHtml(row, "compact-name")}
            <span class="compact-count">${row.count}</span>
            ${label ? `<span class="compact-label">${this._escape(label)}</span>` : ""}
          </li>
        `;
      })
      .join("");

    // The labels explain the order on screen; only e-ink, which has no labels, gets the note.
    const nextNote = this._config.eink && nextBuyers.length > 0 ? this._nextBuyerNote() : "";
    const noteHtml = nextNote ? `<p class="next-note">* ${this._escape(nextNote)}</p>` : "";

    const layout = this._layout();
    const titleText = String(this._config.title || "").trim();
    const showHeader = titleText.length > 0;
    const compactList = compactRowsHtml || '<li class="empty-list compact-empty">No flatmates synced yet.</li>';
    const bodyHtml = layout === "compact"
      ? `
          <div class="body compact-body">
            <ul class="compact-list">
              ${compactList}
            </ul>
            ${noteHtml}
          </div>
        `
      : `
          <div class="body bars-body">
            <ul class="list">
              ${rowsHtml || emptyState}
            </ul>
            ${noteHtml}
          </div>
        `;
    const headerHtml = showHeader
      ? `
          <div class="header">
            <div>
              <h2>${this._escape(titleText)}</h2>
              <p>Based on data of the last ${windowDays} days</p>
            </div>
            <span class="total-chip">${totalCompleted} purchase${totalCompleted === 1 ? "" : "s"}</span>
          </div>
        `
      : "";

    this._root.innerHTML = `
      <ha-card>
        <div class="card ${layout === "compact" ? "compact-layout" : "bars-layout"} ${showHeader ? "with-header" : "without-header"} ${this._config.eink ? "eink" : ""}">
          ${headerHtml}

          ${metaRowHtml}

          ${bodyHtml}
        </div>
        ${this._historyModalHtml(windowDays)}
      </ha-card>

      <style>
        .card {
          display: grid;
          gap: var(--ha-space-3, 12px);
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: var(--ha-space-2, 8px);
          padding: var(--ha-space-4, 16px) var(--ha-space-4, 16px) 0;
        }

        .header h2 {
          margin: 0;
          font-size: var(--ha-font-size-xl, 1.2rem);
          font-weight: var(--ha-font-weight-bold, 700);
          line-height: var(--ha-line-height-condensed, 1.2);
        }

        .header p {
          margin: var(--ha-space-1, 4px) 0 0;
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.85rem);
        }

        .total-chip,
        .chip {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          border-radius: var(--ha-border-radius-pill, 9999px);
          padding: var(--ha-space-1, 4px) var(--ha-space-2, 8px);
          font-size: var(--ha-font-size-xs, 0.75rem);
          line-height: 1;
        }

        .total-chip {
          color: var(--primary-color);
          border-color: rgba(var(--rgb-primary-color, 0, 154, 199), 0.45);
          background: rgba(var(--rgb-primary-color, 0, 154, 199), 0.1);
          font-weight: var(--ha-font-weight-medium, 500);
          white-space: nowrap;
        }

        .meta-row {
          display: flex;
          flex-wrap: wrap;
          gap: var(--ha-space-2, 8px);
          padding: 0 var(--ha-space-4, 16px);
        }

        .chip {
          color: var(--secondary-text-color);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.05);
        }

        .body {
          min-width: 0;
        }

        .bars-body {
          padding: 0 var(--ha-space-4, 16px) var(--ha-space-4, 16px);
        }

        .list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: var(--ha-space-2, 8px);
        }

        .row {
          display: grid;
          gap: var(--ha-space-1, 4px);
        }

        .row-head {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: var(--ha-space-2, 8px);
        }

        .name {
          font-weight: var(--ha-font-weight-medium, 500);
          font-size: var(--ha-font-size-m, 0.875rem);
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .name-wrap {
          display: flex;
          align-items: baseline;
          gap: var(--ha-space-2, 8px);
          min-width: 0;
        }

        .next-chip {
          flex: none;
          font-size: var(--ha-font-size-xs, 0.6875rem);
          font-weight: var(--ha-font-weight-bold, 600);
          padding: 1px var(--ha-space-2, 8px);
          border-radius: var(--ha-border-radius-pill, 9999px);
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          white-space: nowrap;
        }

        .next-chip.then {
          background: none;
          color: var(--primary-color);
          box-shadow: inset 0 0 0 1px var(--primary-color);
        }

        .next-chip.catch-up {
          background: none;
          color: var(--primary-text-color);
          box-shadow: inset 0 0 0 1px var(--secondary-text-color);
        }

        .next-chip.quiet {
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.06);
          color: var(--secondary-text-color);
          font-weight: var(--ha-font-weight-medium, 500);
        }

        .compact-label {
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-xs, 0.6875rem);
          line-height: var(--ha-line-height-condensed, 1.2);
        }

        .compact-cell.next .compact-label {
          color: var(--primary-color);
          font-weight: var(--ha-font-weight-bold, 600);
        }

        .row.next .name {
          font-weight: var(--ha-font-weight-bold, 600);
        }

        .next-note {
          margin: var(--ha-space-2, 8px) 0 0;
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.75rem);
          line-height: var(--ha-line-height-condensed, 1.2);
        }

        .compact-cell.next {
          background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.14);
          box-shadow: inset 0 -3px 0 var(--primary-color);
        }

        .compact-cell.next.then {
          background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.06);
        }

        .compact-cell.next .compact-name {
          font-weight: var(--ha-font-weight-bold, 600);
        }

        .card.eink .next-chip {
          background: #000;
          color: #fff;
        }

        .card.eink .next-chip.then {
          background: #fff;
          color: #000;
          box-shadow: inset 0 0 0 1px #000;
        }

        .card.eink .compact-cell.next {
          background: #000;
          box-shadow: none;
        }

        .card.eink .compact-cell.next .compact-name,
        .card.eink .compact-cell.next .compact-count {
          color: #fff;
        }

        .card.eink .compact-cell.next.then {
          background: #fff;
          box-shadow: inset 0 -4px 0 #000;
        }

        .card.eink .compact-cell.next.then .compact-name,
        .card.eink .compact-cell.next.then .compact-count {
          color: #000;
        }

        .metrics {
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.75rem);
          white-space: nowrap;
          letter-spacing: 0.4px;
        }

        .track {
          height: var(--ha-space-3, 12px);
          border-radius: var(--ha-border-radius-pill, 9999px);
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.06);
          overflow: hidden;
        }

        .fill {
          width: var(--bar-width, 0%);
          height: 100%;
          background: var(--accent);
          transition: width var(--ha-animation-duration-normal, 250ms) ease;
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
          font-size: var(--ha-font-size-s, 0.75rem);
        }

        .compact-list {
          list-style: none;
          margin: 0;
          padding: 0;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: var(--ha-border-radius-md, 8px);
          overflow: hidden;
          background: var(--card-background-color);
          display: flex;
          width: 100%;
        }

        .compact-cell {
          flex: var(--compact-share, 1) 1 0;
          min-width: 0;
          display: grid;
          gap: var(--ha-space-1, 4px);
          text-align: center;
          padding: var(--ha-space-2, 8px) var(--ha-space-1, 4px);
          border-right: 1px solid var(--divider-color, #e0e0e0);
        }

        .compact-cell:last-child {
          border-right: none;
        }

        .compact-name {
          font-weight: var(--ha-font-weight-medium, 500);
          line-height: var(--ha-line-height-condensed, 1.2);
          font-size: clamp(0.56rem, 1.1vw, 0.76rem);
          word-break: break-word;
          overflow-wrap: anywhere;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .compact-count {
          color: var(--secondary-text-color);
          line-height: 1.1;
          font-size: clamp(0.66rem, 1.7vw, 0.9rem);
        }

        .compact-empty {
          padding: var(--ha-space-3, 12px);
        }

        .without-header {
          gap: 0;
        }

        .without-header .meta-row {
          padding-top: var(--ha-space-3, 12px);
          padding-bottom: var(--ha-space-2, 8px);
        }

        .card.eink {
          --divider-color: #000;
          --secondary-text-color: #000;
          --secondary-background-color: #fff;
        }

        .name-btn {
          border: none;
          background: none;
          padding: 0;
          margin: 0;
          font: inherit;
          color: inherit;
          text-align: inherit;
          cursor: pointer;
          text-decoration: underline dotted;
          text-underline-offset: 3px;
        }

        .name-btn:hover,
        .name-btn:focus-visible {
          color: var(--primary-color);
          text-decoration-style: solid;
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
          width: min(480px, 100%);
          max-height: min(80vh, 720px);
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: var(--ha-border-width-sm, 1px) solid var(--divider-color);
          border-radius: var(--ha-border-radius-xl, 16px);
          box-shadow: var(--ha-box-shadow-l, 0 8px 12px rgba(0, 0, 0, 0.14));
          padding: var(--ha-space-4, 16px);
          display: grid;
          grid-template-rows: auto auto minmax(0, 1fr);
          gap: var(--ha-space-3, 12px);
          box-sizing: border-box;
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
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: var(--ha-border-radius-pill, 9999px);
        }

        .history-summary {
          margin: 0;
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.85rem);
        }

        .history-summary strong {
          color: var(--primary-text-color);
        }

        .history-error {
          margin: 0;
          color: var(--error-color, #db4437);
          font-size: var(--ha-font-size-s, 0.85rem);
        }

        .history-scroll {
          overflow-y: auto;
          min-height: 0;
          display: grid;
          gap: var(--ha-space-4, 16px);
          align-content: start;
        }

        .purchase-section-head {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: var(--ha-space-2, 8px);
          padding-bottom: var(--ha-space-1, 4px);
          border-bottom: 2px solid var(--primary-color, #03a9f4);
        }

        .purchase-section.outside-window .purchase-section-head {
          border-bottom-color: var(--divider-color, #e0e0e0);
        }

        .purchase-section-title {
          font-weight: var(--ha-font-weight-bold, 700);
          font-size: var(--ha-font-size-s, 0.85rem);
        }

        .purchase-section-hint {
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-xs, 0.75rem);
        }

        .purchase-list {
          list-style: none;
          margin: 0;
          padding: 0;
        }

        .purchase-row {
          display: flex;
          justify-content: space-between;
          gap: var(--ha-space-3, 12px);
          padding: var(--ha-space-2, 8px) 0;
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
          font-size: var(--ha-font-size-m, 0.875rem);
        }

        .purchase-section.outside-window .purchase-row {
          color: var(--secondary-text-color);
        }

        .purchase-name {
          min-width: 0;
          overflow-wrap: anywhere;
        }

        .purchase-date {
          white-space: nowrap;
          color: var(--secondary-text-color);
          font-variant-numeric: tabular-nums;
        }
      </style>
    `;

    this._bindEvents();
  }
}

class HassFlatmateDistributionCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._editorReady = false;
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_shopping_distribution_90d",
      title: "Shopping Distribution",
      layout: "bars",
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

        <label for="hf-editor-entity">Distribution entity</label>
        <ha-entity-picker id="hf-editor-entity"></ha-entity-picker>

        <label for="hf-editor-layout">Layout style</label>
        <select id="hf-editor-layout">
          <option value="bars" ${this._config.layout === "compact" ? "" : "selected"}>Bars</option>
          <option value="compact" ${this._config.layout === "compact" ? "selected" : ""}>Compact boxes</option>
        </select>

        <label>
          <input id="hf-editor-eink" type="checkbox" ${this._config.eink ? "checked" : ""} />
          E-ink display mode (high contrast)
        </label>

        <label>
          <input id="hf-editor-next-buyer" type="checkbox" ${this._config.show_next_buyer === false ? "" : "checked"} />
          Highlight the two who should buy next
        </label>
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

    const layoutPicker = this._root.querySelector("#hf-editor-layout");
    layoutPicker?.addEventListener("change", (event) => {
      this._emitConfig({
        ...this._config,
        layout: event.target.value || "bars",
      });
    });

    const einkCheckbox = this._root.querySelector("#hf-editor-eink");
    einkCheckbox?.addEventListener("change", (event) => {
      this._emitConfig({
        ...this._config,
        eink: event.target.checked,
      });
    });

    const nextBuyerCheckbox = this._root.querySelector("#hf-editor-next-buyer");
    nextBuyerCheckbox?.addEventListener("change", (event) => {
      this._emitConfig({
        ...this._config,
        show_next_buyer: event.target.checked,
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

    const entityPicker = this._root.querySelector("#hf-editor-entity");
    if (entityPicker) {
      entityPicker.hass = this._hass;
      const nextEntity = this._config.entity || "sensor.hass_flatmate_shopping_distribution_90d";
      if (entityPicker.value !== nextEntity) {
        entityPicker.value = nextEntity;
      }
    }

    const layoutPicker = this._root.querySelector("#hf-editor-layout");
    if (layoutPicker && active !== layoutPicker) {
      const nextLayout = this._config.layout === "compact" ? "compact" : "bars";
      if (layoutPicker.value !== nextLayout) {
        layoutPicker.value = nextLayout;
      }
    }

    const einkCheckbox = this._root.querySelector("#hf-editor-eink");
    if (einkCheckbox) {
      einkCheckbox.checked = !!this._config.eink;
    }

    const nextBuyerCheckbox = this._root.querySelector("#hf-editor-next-buyer");
    if (nextBuyerCheckbox) {
      nextBuyerCheckbox.checked = this._config.show_next_buyer !== false;
    }
  }
}

if (!customElements.get("hass-flatmate-distribution-card")) {
  customElements.define("hass-flatmate-distribution-card", HassFlatmateDistributionCard);
}
if (!customElements.get("hass-flatmate-distribution-card-editor")) {
  customElements.define("hass-flatmate-distribution-card-editor", HassFlatmateDistributionCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hass-flatmate-distribution-card")) {
  window.customCards.push({
    type: "hass-flatmate-distribution-card",
    name: "Hass Flatmate Distribution Card",
    description: "Shopping fairness card with bars or compact single-row boxes.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#distribution-ui-card",
  });
}
