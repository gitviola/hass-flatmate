class HassFlatmateDistributionCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
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
    });
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

  _number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
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

    const rowsHtml = distribution
      .map((row, idx) => {
        const relativeWidth = maxCount > 0 ? (row.count / maxCount) * 100 : 0;
        const barWidth = row.count > 0
          ? Math.max(6, Math.min(100, relativeWidth))
          : 0;
        const accent = palette[idx % palette.length];

        return `
          <li class="row" style="--accent:${accent}; --bar-width:${barWidth}%;">
            <div class="row-head">
              <span class="name">${this._escape(row.name)}</span>
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
      .map(
        (row, idx) => `
          <li class="compact-cell" style="--compact-share:${compactShares[idx] || 0};">
            <span class="compact-name">${this._escape(row.name)}</span>
            <span class="compact-count">${row.count}</span>
          </li>
        `
      )
      .join("");

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
          </div>
        `
      : `
          <div class="body bars-body">
            <ul class="list">
              ${rowsHtml || emptyState}
            </ul>
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
        <div class="card ${layout === "compact" ? "compact-layout" : "bars-layout"} ${showHeader ? "with-header" : "without-header"}">
          ${headerHtml}

          ${metaRowHtml}

          ${bodyHtml}
        </div>
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
      </style>
    `;
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
