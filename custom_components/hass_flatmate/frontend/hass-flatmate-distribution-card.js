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
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Shopping Distribution",
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return 6;
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
      const percent = Math.max(0, Math.min(100, this._number(row?.percent, 0)));
      const memberId = row?.member_id;
      return { name, count, percent, memberId };
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
        const percentFromCount = totalCompleted > 0 ? (row.count / totalCompleted) * 100 : 0;
        const effectivePercent = totalCompleted > 0 ? Math.max(row.percent, percentFromCount) : 0;
        const barWidth = row.count > 0
          ? Math.max(6, Math.min(100, effectivePercent))
          : 0;
        const countRatio = row.count / maxCount;
        const accent = palette[idx % palette.length];

        return `
          <li class="row" style="--accent:${accent}; --bar-width:${barWidth}%; --count-ratio:${countRatio};">
            <div class="row-head">
              <span class="name">${this._escape(row.name)}</span>
              <span class="metrics">${row.count} • ${effectivePercent.toFixed(totalCompleted > 0 ? 1 : 0)}%</span>
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

    this._root.innerHTML = `
      <ha-card>
        <div class="card">
          <div class="header">
            <div>
              <h2>${this._escape(this._config.title)}</h2>
              <p>Last ${windowDays} days</p>
            </div>
            <span class="total-chip">${totalCompleted} done</span>
          </div>

          <div class="meta-row">
            <span class="chip">Window: ${windowDays}d</span>
            ${unknownBadge}
          </div>

          <ul class="list">
            ${rowsHtml || emptyState}
          </ul>
        </div>
      </ha-card>

      <style>
        .card {
          padding: 16px;
          display: grid;
          gap: 12px;
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
          font-size: 0.88rem;
        }

        .total-chip,
        .chip {
          border: 1px solid var(--divider-color);
          border-radius: 999px;
          padding: 5px 10px;
          font-size: 0.78rem;
          line-height: 1;
        }

        .total-chip {
          color: var(--primary-color);
          border-color: color-mix(in srgb, var(--primary-color) 45%, var(--divider-color));
          background: color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color));
          font-weight: 600;
          white-space: nowrap;
        }

        .meta-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .chip {
          color: var(--secondary-text-color);
          background: color-mix(in srgb, var(--divider-color) 10%, var(--card-background-color));
        }

        .list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 10px;
        }

        .row {
          display: grid;
          gap: 6px;
        }

        .row-head {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 10px;
        }

        .name {
          font-weight: 600;
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .metrics {
          color: var(--secondary-text-color);
          font-size: 0.82rem;
          white-space: nowrap;
        }

        .track {
          height: 12px;
          border-radius: 999px;
          border: 1px solid var(--divider-color);
          background: color-mix(in srgb, var(--divider-color) 16%, var(--card-background-color));
          overflow: hidden;
        }

        .fill {
          width: var(--bar-width, 0%);
          height: 100%;
          background: color-mix(in srgb, var(--accent) 80%, #ffffff 20%);
          transition: width 260ms ease;
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
        }
      </style>
    `;
  }
}

class HassFlatmateDistributionCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_shopping_distribution_90d",
      title: "Shopping Distribution",
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

        <label for="hf-editor-entity">Distribution entity</label>
        <ha-entity-picker id="hf-editor-entity"></ha-entity-picker>
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

    const entityPicker = this._root.querySelector("#hf-editor-entity");
    if (entityPicker) {
      entityPicker.hass = this._hass;
      entityPicker.value = this._config.entity || "sensor.hass_flatmate_shopping_distribution_90d";
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
    description: "Shopping fairness bars for all flatmates without relying on SVG image cards.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#distribution-ui-card",
  });
}
