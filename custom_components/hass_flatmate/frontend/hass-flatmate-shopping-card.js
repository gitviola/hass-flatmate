class HassFlatmateShoppingCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._draftName = "";
    this._busy = false;
    this._errorMessage = "";
    this._stateSnapshot = "";
  }

  static async getConfigElement() {
    return document.createElement("hass-flatmate-shopping-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.hass_flatmate_shopping_data",
      title: "Shopping List",
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Missing required 'entity' in card config");
    }
    this._config = {
      title: "Shopping List",
      ...config,
    };
    this._stateSnapshot = "";
    this._render();
  }

  getCardSize() {
    return 7;
  }

  set hass(hass) {
    const nextSnapshot = this._buildStateSnapshot(hass);
    const inputIsFocused = this._root?.activeElement?.id === "hf-item-input";
    this._hass = hass;
    if (!this._config) {
      return;
    }
    if (inputIsFocused && nextSnapshot === this._stateSnapshot) {
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
      suggestions: attrs.suggestions || [],
      service_domain: attrs.service_domain || "",
      service_add_item: attrs.service_add_item || "",
      service_complete_item: attrs.service_complete_item || "",
      service_delete_item: attrs.service_delete_item || "",
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
      addItem: attributes.service_add_item || "hass_flatmate_add_shopping_item",
      completeItem: attributes.service_complete_item || "hass_flatmate_complete_shopping_item",
      deleteItem: attributes.service_delete_item || "hass_flatmate_delete_shopping_item",
    };
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
    const abs = Math.abs(diffSeconds);
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

    const units = [
      [60, "second"],
      [60, "minute"],
      [24, "hour"],
      [7, "day"],
      [4.34524, "week"],
      [12, "month"],
      [Number.POSITIVE_INFINITY, "year"],
    ];

    let value = diffSeconds;
    let unit = "second";
    let current = abs;

    for (const [base, nextUnit] of units) {
      unit = nextUnit;
      if (current < base) {
        break;
      }
      value = Math.round(value / base);
      current = current / base;
    }

    return `added ${rtf.format(-Math.abs(value), unit)}`;
  }

  async _callService(service, data) {
    if (!this._hass || !this._stateObj) {
      return;
    }
    const meta = this._serviceMeta(this._stateObj.attributes || {});
    await this._hass.callService(meta.domain, service, data);
    this._errorMessage = "";
  }

  async _addItem(name) {
    const normalized = String(name || "").trim();
    if (!normalized) {
      return;
    }

    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.addItem, { name: normalized });
      this._draftName = "";
    } catch (error) {
      this._errorMessage = error?.message || "Unable to add shopping item";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _completeItem(id) {
    if (!id) {
      return;
    }
    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.completeItem, { item_id: id });
    } catch (error) {
      this._errorMessage = error?.message || "Unable to mark item as bought";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _deleteItem(id, name) {
    if (!id) {
      return;
    }
    const confirmed = window.confirm(`Remove "${name}" from the shopping list?`);
    if (!confirmed) {
      return;
    }

    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.deleteItem, { item_id: id });
    } catch (error) {
      this._errorMessage = error?.message || "Unable to remove item";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _bindEvents() {
    const form = this._root.querySelector("#hf-add-form");
    const input = this._root.querySelector("#hf-item-input");
    const stopBubble = (event) => event.stopPropagation();

    input?.addEventListener("input", (event) => {
      this._draftName = event.target.value;
    });
    input?.addEventListener("click", stopBubble);
    input?.addEventListener("focus", stopBubble);
    input?.addEventListener("mousedown", stopBubble);
    input?.addEventListener("pointerdown", stopBubble);
    input?.addEventListener("keydown", stopBubble);
    input?.addEventListener("keyup", stopBubble);
    input?.addEventListener("keypress", stopBubble);
    form?.addEventListener("click", stopBubble);
    form?.addEventListener("mousedown", stopBubble);
    form?.addEventListener("pointerdown", stopBubble);

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await this._addItem(this._draftName);
    });

    this._root.querySelectorAll("[data-action='add-quick']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._addItem(el.dataset.name);
      });
    });

    this._root.querySelectorAll("[data-action='complete-item']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._completeItem(Number(el.dataset.itemId));
      });
    });

    this._root.querySelectorAll("[data-action='delete-item']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._deleteItem(Number(el.dataset.itemId), el.dataset.itemName || "item");
      });
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

    const activeElement = this._root.activeElement;
    const shouldRestoreInputFocus = activeElement?.id === "hf-item-input";
    const selectionStart = shouldRestoreInputFocus ? activeElement.selectionStart : null;
    const selectionEnd = shouldRestoreInputFocus ? activeElement.selectionEnd : null;

    const attrs = this._stateObj.attributes || {};
    const openItems = Array.isArray(attrs.open_items) ? attrs.open_items : [];
    const rawRecents = Array.isArray(attrs.suggestions) ? attrs.suggestions : [];
    const openNameSet = new Set(
      openItems
        .map((item) => String(item?.name || "").trim().toLowerCase())
        .filter((name) => name.length > 0)
    );
    const seenRecentNames = new Set();
    const recents = rawRecents
      .map((name) => String(name || "").trim())
      .filter((name) => name.length > 0)
      .filter((name) => {
        const key = name.toLowerCase();
        if (seenRecentNames.has(key)) {
          return false;
        }
        seenRecentNames.add(key);
        return true;
      })
      .filter((name) => !openNameSet.has(name.toLowerCase()));
    const openCount = Number.parseInt(this._stateObj.state, 10) || openItems.length;

    const itemRows = openItems
      .map((item) => {
        const id = Number(item.id);
        const itemName = String(item.name || "");
        const name = this._escape(itemName);
        const relative = this._relativeAdded(item.added_at);
        const addedBy = item.added_by_name ? ` by ${this._escape(item.added_by_name)}` : "";
        return `
          <li class="item-row">
            <div class="item-main">
              <div class="item-name">${name}</div>
              <div class="item-meta">${this._escape(relative)}${addedBy}</div>
            </div>
            <div class="item-actions">
              <button class="todo-check" type="button" data-action="complete-item" data-item-id="${id}" title="Mark as bought" aria-label="Mark ${name} as bought" ${this._busy ? "disabled" : ""}><ha-icon icon="mdi:check-circle-outline"></ha-icon></button>
              <button class="todo-delete" type="button" data-action="delete-item" data-item-id="${id}" data-item-name="${name}" title="Remove item" aria-label="Remove ${name} from shopping list" ${this._busy ? "disabled" : ""}><ha-icon icon="mdi:trash-can-outline"></ha-icon></button>
            </div>
          </li>
        `;
      })
      .join("");

    const quickChips = recents
      .slice(0, 20)
      .map((name) => {
        const escaped = this._escape(name);
        return `<button class="chip" type="button" data-action="add-quick" data-name="${escaped}" ${this._busy ? "disabled" : ""}>${escaped}</button>`;
      })
      .join("");

    const draftName = this._escape(this._draftName || "");
    const disabledAttr = this._busy ? "disabled" : "";
    const errorMessage = this._errorMessage ? this._escape(this._errorMessage) : "";
    const suggestionOptions = recents
      .slice(0, 40)
      .map((name) => `<option value="${this._escape(name)}"></option>`)
      .join("");

    this._root.innerHTML = `
      <ha-card>
        <div class="card">
          <div class="header">
            <h2>${this._escape(this._config.title)}</h2>
            <p>${openCount} open item${openCount === 1 ? "" : "s"}</p>
          </div>

          <section>
            <h3>Open items</h3>
            <ul class="item-list">
              ${itemRows || '<li class="empty-list">Nothing to buy right now</li>'}
            </ul>
          </section>

          <section>
            <h3>Add item</h3>
            <form id="hf-add-form" class="add-row" autocomplete="off">
              <input id="hf-item-input" type="text" list="hf-item-suggestions" placeholder="Type an item" value="${draftName}" ${disabledAttr} />
              <datalist id="hf-item-suggestions">${suggestionOptions}</datalist>
              <button class="add-btn" type="submit" ${disabledAttr}>Add</button>
            </form>
          </section>

          <section>
            <h3>Recent items</h3>
            <div class="chips-wrap">
              ${quickChips || '<span class="empty-list">No recent items yet</span>'}
            </div>
          </section>

          ${errorMessage ? `<div class="error">${errorMessage}</div>` : ""}
        </div>
      </ha-card>

      <style>
        .card {
          padding: 16px;
          display: grid;
          gap: 14px;
        }

        .header h2 {
          margin: 0;
          font-size: 1.2rem;
          line-height: 1.3;
        }

        .header p {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
          font-size: 0.92rem;
        }

        section h3 {
          margin: 0 0 8px;
          font-size: 0.92rem;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .item-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 8px;
        }

        .item-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 10px;
          align-items: center;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          padding: 10px;
        }

        .item-actions {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .item-main {
          min-width: 0;
        }

        .item-name {
          font-weight: 600;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .item-meta {
          margin-top: 2px;
          color: var(--secondary-text-color);
          font-size: 0.83rem;
        }

        .todo-check,
        .todo-delete,
        .add-btn,
        .chip {
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 10px;
          padding: 6px 9px;
          cursor: pointer;
          font: inherit;
        }

        .todo-check {
          min-width: 34px;
          min-height: 34px;
          line-height: 0;
          color: var(--success-color, #4caf50);
          border-color: color-mix(in srgb, var(--success-color, #4caf50) 45%, var(--divider-color));
          background: color-mix(in srgb, var(--success-color, #4caf50) 14%, var(--card-background-color));
        }

        .todo-delete {
          min-width: 34px;
          min-height: 34px;
          line-height: 0;
          color: var(--secondary-text-color);
          border-color: transparent;
          background: transparent;
        }

        .todo-check:hover,
        .add-btn:hover,
        .chip:hover {
          border-color: var(--primary-color);
        }

        .todo-delete:hover {
          border-color: var(--divider-color);
          color: var(--primary-text-color);
          background: color-mix(in srgb, var(--divider-color) 20%, transparent);
        }

        .add-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 8px;
        }

        #hf-item-input {
          box-sizing: border-box;
          width: 100%;
          min-height: 42px;
          border-radius: 10px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          padding: 10px 12px;
        }

        #hf-item-input:focus {
          outline: none;
          border-color: var(--primary-color);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 55%, transparent);
        }

        .add-btn {
          background: color-mix(in srgb, var(--primary-color) 18%, var(--card-background-color));
        }

        .chips-wrap {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
        }

        .error {
          border: 1px solid color-mix(in srgb, var(--error-color, #f44336) 40%, var(--divider-color));
          color: var(--error-color, #f44336);
          background: color-mix(in srgb, var(--error-color, #f44336) 8%, var(--card-background-color));
          border-radius: 10px;
          padding: 8px 10px;
          font-size: 0.9rem;
        }

        @media (max-width: 700px) {
          .add-row {
            grid-template-columns: 1fr;
          }
        }
      </style>
    `;

    this._bindEvents();

    if (shouldRestoreInputFocus) {
      const nextInput = this._root.querySelector("#hf-item-input");
      if (nextInput) {
        nextInput.focus({ preventScroll: true });
        if (selectionStart !== null && selectionEnd !== null) {
          try {
            nextInput.setSelectionRange(selectionStart, selectionEnd);
          } catch (_error) {}
        }
      }
    }
  }
}

class HassFlatmateShoppingCardEditor extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_shopping_data",
      title: "Shopping List",
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
      entityPicker.hass = this._hass;
      entityPicker.value = this._config.entity || "sensor.hass_flatmate_shopping_data";
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

if (!customElements.get("hass-flatmate-shopping-card")) {
  customElements.define("hass-flatmate-shopping-card", HassFlatmateShoppingCard);
}
if (!customElements.get("hass-flatmate-shopping-card-editor")) {
  customElements.define("hass-flatmate-shopping-card-editor", HassFlatmateShoppingCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hass-flatmate-shopping-card")) {
  window.customCards.push({
    type: "hass-flatmate-shopping-card",
    name: "Hass Flatmate Shopping Card",
    description: "Todo-like shopping list with quick add and completion actions.",
    preview: true,
    configurable: true,
    documentationURL: "https://github.com/gitviola/hass-flatmate#shopping-ui-card",
  });
}
