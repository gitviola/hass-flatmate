class HassFlatmateShoppingCompactCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._stateSnapshot = "";
  }

  static async getConfigElement() {
    return document.createElement("hass-flatmate-shopping-compact-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hass_flatmate_shopping_data",
      title: "Shopping List (Compact)",
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Shopping List (Compact)",
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return 4;
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
      open_items: attrs.open_items || [],
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

  _relativeAdded(isoString) {
    if (!isoString) {
      return "added recently";
    }

    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return "added recently";
    }

    const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000);
    const absSeconds = Math.abs(diffSeconds);
    if (absSeconds < 45) {
      return "added just now";
    }

    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    const units = [
      ["year", 31_536_000],
      ["month", 2_592_000],
      ["week", 604_800],
      ["day", 86_400],
      ["hour", 3_600],
      ["minute", 60],
    ];

    for (const [unit, secondsPerUnit] of units) {
      if (absSeconds >= secondsPerUnit) {
        const value = Math.round(diffSeconds / secondsPerUnit);
        return `added ${rtf.format(-Math.abs(value), unit)}`;
      }
    }

    return "added recently";
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
    const titleText = String(this._config.title || "").trim();
    const openItems = (Array.isArray(attrs.open_items) ? attrs.open_items : [])
      .map((item) => ({
        id: item?.id,
        name: String(item?.name || "").trim() || "Unnamed item",
        addedAt: item?.added_at,
      }))
      .sort((a, b) => String(a.addedAt || "").localeCompare(String(b.addedAt || "")));

    const rowsHtml = openItems
      .map(
        (item) => `
          <li class="item-row" data-item-id="${this._escape(item.id)}">
            <div class="item-main">
              <span class="item-name">${this._escape(item.name)}</span>
              <span class="item-age">${this._escape(this._relativeAdded(item.addedAt))}</span>
            </div>
          </li>
        `
      )
      .join("");

    const headerHtml = titleText
      ? `
          <div class="header">
            <h2>${this._escape(titleText)}</h2>
            <span class="count-chip">${openItems.length}</span>
          </div>
        `
      : "";

    this._root.innerHTML = `
      <ha-card>
        <div class="card ${titleText ? "with-title" : "without-title"}">
          ${headerHtml}

          <ul class="list">
            ${rowsHtml || '<li class="empty-list">The list is empty.</li>'}
          </ul>
        </div>
      </ha-card>

      <style>
        .card {
          display: grid;
          gap: 8px;
          padding: 10px;
        }

        .card.without-title {
          gap: 0;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
        }

        .header h2 {
          margin: 0;
          font-size: 1rem;
          line-height: 1.2;
          font-weight: 700;
        }

        .count-chip {
          border: 2px solid var(--primary-text-color, #000);
          border-radius: 0;
          padding: 2px 8px;
          font-size: 0.75rem;
          font-weight: 700;
          line-height: 1.1;
          min-width: 1.8em;
          text-align: center;
        }

        .list {
          list-style: none;
          margin: 0;
          padding: 0;
          border: 2px solid var(--primary-text-color, #000);
          border-radius: 0;
          overflow: hidden;
        }

        .item-row {
          margin: 0;
          padding: 6px 8px;
          border-bottom: 1px solid var(--primary-text-color, #000);
        }

        .item-row:last-child {
          border-bottom: none;
        }

        .item-main {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          align-items: baseline;
          gap: 8px;
        }

        .item-name {
          font-weight: 650;
          font-size: 0.9rem;
          line-height: 1.2;
          overflow-wrap: anywhere;
        }

        .item-age {
          color: var(--secondary-text-color);
          font-size: 0.72rem;
          line-height: 1.2;
          white-space: nowrap;
          text-align: right;
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
        }

        .empty-list {
          padding: 8px 10px;
          border: 2px solid var(--primary-text-color, #000);
          border-radius: 0;
          list-style: none;
        }

        @media (max-width: 480px) {
          .item-main {
            grid-template-columns: 1fr;
            gap: 4px;
          }

          .item-age {
            text-align: left;
            white-space: normal;
          }
        }
      </style>
    `;
  }
}

class HassFlatmateShoppingCompactCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._editorReady = false;
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_shopping_data",
      title: "Shopping List (Compact)",
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

        <label for="hf-editor-entity">Data entity</label>
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
      const nextEntity = this._config.entity || "sensor.hass_flatmate_shopping_data";
      if (entityPicker.value !== nextEntity) {
        entityPicker.value = nextEntity;
      }
    }
  }
}

if (!customElements.get("hass-flatmate-shopping-compact-card")) {
  customElements.define("hass-flatmate-shopping-compact-card", HassFlatmateShoppingCompactCard);
}
if (!customElements.get("hass-flatmate-shopping-compact-card-editor")) {
  customElements.define(
    "hass-flatmate-shopping-compact-card-editor",
    HassFlatmateShoppingCompactCardEditor
  );
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hass-flatmate-shopping-compact-card")) {
  window.customCards.push({
    type: "hass-flatmate-shopping-compact-card",
    name: "Hass Flatmate Shopping Compact",
    description: "Read-only compact shopping list card with relative added times.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#shopping-compact-ui-card",
  });
}
