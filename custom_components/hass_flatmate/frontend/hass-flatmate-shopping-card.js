class HassFlatmateShoppingCard extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._draftName = "";
    this._errorMessage = "";
    this._stateSnapshot = "";
    this._pendingItemIds = new Set();
    this._pendingAdds = [];
    this._deferredSnapshot = "";
    this._optimisticRecents = [];
    this._historyModalOpen = false;
    this._historyModalItemName = "";
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

    if (inputIsFocused) {
      if (nextSnapshot !== this._stateSnapshot) {
        this._deferredSnapshot = nextSnapshot;
      }
      return;
    }

    if (this._deferredSnapshot && this._deferredSnapshot !== this._stateSnapshot) {
      this._stateSnapshot = this._deferredSnapshot;
      this._deferredSnapshot = "";
      this._render();
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
      item_history: attrs.item_history || {},
      history_modal_open: this._historyModalOpen,
      history_modal_item_name: this._historyModalItemName,
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

  _normalizeName(value) {
    const name = String(value || "").trim();
    return {
      name,
      key: name.toLowerCase(),
    };
  }

  _pushOptimisticRecent(name) {
    const normalized = this._normalizeName(name);
    if (!normalized.name) {
      return null;
    }
    const token = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    this._optimisticRecents = [
      { token, key: normalized.key, name: normalized.name },
      ...this._optimisticRecents.filter((entry) => entry.key !== normalized.key),
    ].slice(0, 120);
    return token;
  }

  _dropOptimisticRecentByToken(token) {
    if (!token) {
      return;
    }
    this._optimisticRecents = this._optimisticRecents.filter((entry) => entry.token !== token);
  }

  _dropOptimisticRecentByName(name) {
    const normalized = this._normalizeName(name);
    if (!normalized.key) {
      return;
    }
    this._optimisticRecents = this._optimisticRecents.filter((entry) => entry.key !== normalized.key);
  }

  _toTimestamp(value) {
    const parsed = Date.parse(String(value || ""));
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  _sortOpenItems(items) {
    return [...items].sort((a, b) => {
      const aPending = a?.pending_add ? 1 : 0;
      const bPending = b?.pending_add ? 1 : 0;
      if (aPending !== bPending) {
        return bPending - aPending;
      }

      const byDate = this._toTimestamp(b?.added_at) - this._toTimestamp(a?.added_at);
      if (byDate !== 0) {
        return byDate;
      }

      return String(a?.name || "").localeCompare(String(b?.name || ""), undefined, {
        sensitivity: "base",
      });
    });
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

  _relativeTime(isoDatetime) {
    if (!isoDatetime) {
      return "";
    }
    const date = new Date(isoDatetime);
    if (Number.isNaN(date.getTime())) {
      return "";
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
    return rtf.format(-Math.abs(value), unit);
  }

  _openHistoryModal(itemName) {
    this._historyModalOpen = true;
    this._historyModalItemName = String(itemName || "");
    this._stateSnapshot = "";
    this._render();
  }

  _closeHistoryModal() {
    this._historyModalOpen = false;
    this._historyModalItemName = "";
    this._stateSnapshot = "";
    this._render();
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

    const key = normalized.toLowerCase();
    this._dropOptimisticRecentByName(normalized);
    if (this._pendingAdds.some((row) => row.key === key)) {
      return;
    }
    const openItems = Array.isArray(this._stateObj?.attributes?.open_items)
      ? this._stateObj.attributes.open_items
      : [];
    const currentOpenCount = openItems.filter(
      (item) => String(item?.name || "").trim().toLowerCase() === key
    ).length;
    const currentPendingCount = this._pendingAdds.filter((row) => row.key === key).length;
    const tempId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    this._pendingAdds.push({
      tempId,
      key,
      name: normalized,
      addedAt: new Date().toISOString(),
      expectedOpenCount: currentOpenCount + currentPendingCount + 1,
    });

    this._draftName = "";
    this._errorMessage = "";
    this._render();

    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.addItem, { name: normalized });
    } catch (error) {
      this._pendingAdds = this._pendingAdds.filter((row) => row.tempId !== tempId);
      this._draftName = normalized;
      this._errorMessage = error?.message || "Unable to add shopping item";
      this._render();
    }
  }

  async _completeItem(id, name = "", buttonEl = null) {
    if (!id || this._pendingItemIds.has(id)) {
      return;
    }

    // Animate: swap icon to checkmark, pop the button, fade out the row
    const rowEl = buttonEl?.closest(".item-row");
    if (buttonEl) {
      const icon = buttonEl.querySelector("ha-icon");
      if (icon) {
        icon.setAttribute("icon", "mdi:check-circle");
      }
      buttonEl.classList.add("completing");
    }
    if (rowEl) {
      rowEl.classList.add("fade-out");
    }

    // Wait for animation before removing
    await new Promise((resolve) => setTimeout(resolve, 420));

    const optimisticRecentToken = this._pushOptimisticRecent(name);
    this._errorMessage = "";
    this._pendingItemIds.add(id);
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.completeItem, { item_id: id });
    } catch (error) {
      this._dropOptimisticRecentByToken(optimisticRecentToken);
      this._pendingItemIds.delete(id);
      this._errorMessage = error?.message || "Unable to mark item as bought";
      this._render();
    }
  }

  async _deleteItem(id, name) {
    if (!id || this._pendingItemIds.has(id)) {
      return;
    }
    const confirmed = window.confirm(`Remove "${name}" from the shopping list?`);
    if (!confirmed) {
      return;
    }

    const optimisticRecentToken = this._pushOptimisticRecent(name);
    this._errorMessage = "";
    this._pendingItemIds.add(id);
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.deleteItem, { item_id: id });
    } catch (error) {
      this._dropOptimisticRecentByToken(optimisticRecentToken);
      this._pendingItemIds.delete(id);
      this._errorMessage = error?.message || "Unable to remove item";
      this._render();
    }
  }

  _renderHistoryModal() {
    if (!this._historyModalOpen || !this._historyModalItemName) {
      return "";
    }
    const attrs = this._stateObj?.attributes || {};
    const itemHistory = attrs.item_history || {};
    const nameKey = this._historyModalItemName.trim().toLowerCase();
    const entries = itemHistory[nameKey] || [];
    const displayName = this._escape(this._historyModalItemName);

    const entriesHtml = entries.length > 0
      ? entries.map((entry) => {
          const memberName = this._escape(entry.completed_by_name || "Someone");
          const relTime = this._relativeTime(entry.completed_at);
          return `
            <li class="history-entry">
              <ha-icon icon="mdi:cart-check" class="history-icon"></ha-icon>
              <div class="history-entry-content">
                <span class="history-member">${memberName}</span>
                <span class="history-time">${this._escape(relTime)}</span>
              </div>
            </li>
          `;
        }).join("")
      : '<li class="history-empty">No purchase history available</li>';

    return `
      <div class="history-backdrop" data-action="close-history-modal"></div>
      <div class="history-modal">
        <div class="history-modal-header">
          <h3>${displayName}</h3>
          <button class="history-modal-close" type="button" data-action="close-history-modal" aria-label="Close">
            <ha-icon icon="mdi:close"></ha-icon>
          </button>
        </div>
        <ul class="history-list">
          ${entriesHtml}
        </ul>
        <div class="history-modal-footer">
          <button class="history-modal-close-btn" type="button" data-action="close-history-modal">Close</button>
        </div>
      </div>
    `;
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
    input?.addEventListener("blur", () => {
      window.setTimeout(() => {
        if (this._deferredSnapshot && this._deferredSnapshot !== this._stateSnapshot) {
          this._stateSnapshot = this._deferredSnapshot;
          this._deferredSnapshot = "";
        }
        this._render();
      }, 120);
    });
    input?.addEventListener("mousedown", stopBubble);
    input?.addEventListener("pointerdown", stopBubble);
    input?.addEventListener("keydown", (event) => {
      stopBubble(event);
    });
    input?.addEventListener("keyup", stopBubble);
    input?.addEventListener("keypress", stopBubble);
    input?.addEventListener("beforeinput", stopBubble);
    form?.addEventListener("click", stopBubble);
    form?.addEventListener("mousedown", stopBubble);
    form?.addEventListener("pointerdown", stopBubble);

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await this._addItem(this._draftName);
    });

    this._root.querySelectorAll("[data-action='add-quick']").forEach((el) => {
      el.addEventListener("click", () => {
        this._addItem(el.dataset.name);
      });
    });

    this._root.querySelectorAll("[data-action='complete-item']").forEach((el) => {
      el.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this._completeItem(Number(el.dataset.itemId), el.dataset.itemName || "", el);
      });
    });

    this._root.querySelectorAll("[data-action='delete-item']").forEach((el) => {
      el.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this._deleteItem(Number(el.dataset.itemId), el.dataset.itemName || "item");
      });
    });

    this._root.querySelectorAll("li[data-action='open-item-history']").forEach((el) => {
      el.addEventListener("click", () => {
        this._openHistoryModal(el.dataset.itemName || "");
      });
    });

    this._root.querySelectorAll("[data-action='close-history-modal']").forEach((el) => {
      el.addEventListener("click", () => {
        this._closeHistoryModal();
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

    const openCountByName = new Map();
    for (const item of openItems) {
      const key = String(item?.name || "").trim().toLowerCase();
      if (!key) {
        continue;
      }
      openCountByName.set(key, (openCountByName.get(key) || 0) + 1);
    }
    this._pendingAdds = this._pendingAdds.filter(
      (row) => (openCountByName.get(row.key) || 0) < row.expectedOpenCount
    );

    const pendingOpenItems = this._pendingAdds.map((row) => ({
      id: `pending-${row.tempId}`,
      name: row.name,
      added_at: row.addedAt,
      added_by_name: null,
      pending_add: true,
    }));

    const openIdSet = new Set(
      openItems
        .map((item) => Number(item?.id))
        .filter((id) => Number.isInteger(id) && id > 0)
    );
    for (const pendingId of [...this._pendingItemIds]) {
      if (!openIdSet.has(pendingId)) {
        this._pendingItemIds.delete(pendingId);
      }
    }

    const visibleOpenItems = openItems.filter(
      (item) => !this._pendingItemIds.has(Number(item?.id))
    );
    const renderedOpenItems = this._sortOpenItems([...pendingOpenItems, ...visibleOpenItems]);

    const rawRecents = Array.isArray(attrs.suggestions) ? attrs.suggestions : [];
    const rawRecentRows = rawRecents
      .map((name) => this._normalizeName(name))
      .filter((row) => row.name);
    const rawRecentKeySet = new Set(rawRecentRows.map((row) => row.key));
    const openNameSet = new Set(
      renderedOpenItems
        .map((item) => String(item?.name || "").trim().toLowerCase())
        .filter((name) => name.length > 0)
    );
    this._optimisticRecents = this._optimisticRecents
      .filter((entry) => !openNameSet.has(entry.key))
      .filter((entry) => !rawRecentKeySet.has(entry.key))
      .slice(0, 120);
    const seenRecentNames = new Set();
    const mergedRecents = [
      ...this._optimisticRecents.map((entry) => ({ name: entry.name, key: entry.key })),
      ...rawRecentRows,
    ];
    const recents = mergedRecents
      .filter((name) => {
        const key = name.key;
        if (seenRecentNames.has(key)) {
          return false;
        }
        seenRecentNames.add(key);
        return true;
      })
      .filter((name) => !openNameSet.has(name.key))
      .map((row) => row.name);
    const openCount = renderedOpenItems.length;

    const itemRows = renderedOpenItems
      .map((item) => {
        const id = Number(item.id);
        const itemName = String(item.name || "");
        const name = this._escape(itemName);
        const relative = this._relativeAdded(item.added_at);
        const isPendingAdd = Boolean(item.pending_add);
        const addedBy = item.added_by_name ? ` by ${this._escape(item.added_by_name)}` : "";
        const metaText = isPendingAdd ? "adding..." : `${this._escape(relative)}${addedBy}`;
        const actionButtons = isPendingAdd
          ? '<span class="pending-pill">Saving...</span>'
          : `
              <button class="todo-check" type="button" data-action="complete-item" data-item-id="${id}" data-item-name="${name}" title="Mark as bought" aria-label="Mark ${name} as bought"><ha-icon icon="mdi:circle-outline"></ha-icon></button>
              <button class="todo-delete" type="button" data-action="delete-item" data-item-id="${id}" data-item-name="${name}" title="Remove from shopping list" aria-label="Remove ${name} from shopping list"><ha-icon icon="mdi:close-circle-outline"></ha-icon></button>
            `;
        return `
          <li class="item-row ${isPendingAdd ? "pending-add" : ""}" data-action="open-item-history" data-item-name="${name}">
            <div class="item-main">
              <div class="item-name">${name}</div>
              <div class="item-meta">${metaText}</div>
            </div>
            <div class="item-actions">
              ${actionButtons}
            </div>
          </li>
        `;
      })
      .join("");

    const quickChips = recents
      .slice(0, 20)
      .map((name) => {
        const escaped = this._escape(name);
        return `<button class="chip" type="button" data-action="add-quick" data-name="${escaped}">${escaped}</button>`;
      })
      .join("");

    const draftName = this._escape(this._draftName || "");
    const errorMessage = this._errorMessage ? this._escape(this._errorMessage) : "";
    const datalistOptions = recents
      .slice(0, 60)
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
              <div class="add-field">
                <input id="hf-item-input" list="hf-item-suggestions" type="text" placeholder="Type an item" value="${draftName}" autocomplete="off" autocapitalize="none" spellcheck="false" />
                <datalist id="hf-item-suggestions">
                  ${datalistOptions}
                </datalist>
              </div>
              <button class="add-btn" type="submit">Add</button>
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
        ${this._renderHistoryModal()}
      </ha-card>

      <style>
        ha-card {
          box-shadow: none;
          border: none;
          background: transparent;
        }

        .card {
          padding: var(--ha-space-4, 16px);
          display: grid;
          gap: var(--ha-space-3, 12px);
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

        section h3 {
          margin: 0 0 var(--ha-space-2, 8px);
          font-size: var(--ha-font-size-s, 0.85rem);
          font-weight: var(--ha-font-weight-medium, 500);
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .item-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: var(--ha-space-2, 8px);
        }

        .item-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: var(--ha-space-2, 8px);
          align-items: center;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
          border-radius: var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px));
          box-shadow: var(--ha-card-box-shadow, none);
          padding: var(--ha-space-3, 12px);
          cursor: pointer;
          transition: box-shadow var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      border-color var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      background var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .item-row:hover {
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.04);
        }

        .item-row.pending-add {
          opacity: 0.72;
        }

        .item-actions {
          display: inline-flex;
          align-items: center;
          gap: var(--ha-space-1, 4px);
          position: relative;
          z-index: 1;
        }

        .item-main {
          min-width: 0;
        }

        .item-name {
          font-weight: var(--ha-font-weight-medium, 500);
          font-size: var(--ha-font-size-m, 0.875rem);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .item-meta {
          margin-top: 2px;
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.75rem);
          line-height: var(--ha-line-height-condensed, 1.2);
          letter-spacing: 0.4px;
        }

        .todo-check,
        .todo-delete,
        .add-btn,
        .pending-pill,
        .chip {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: var(--ha-border-radius-pill, 9999px);
          padding: var(--ha-space-1, 4px) var(--ha-space-2, 8px);
          cursor: pointer;
          font: inherit;
          font-size: var(--ha-font-size-s, 0.75rem);
          transition: border-color var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      background var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      color var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .todo-check {
          min-width: 36px;
          min-height: 36px;
          line-height: 0;
          color: var(--secondary-text-color);
          border-color: var(--outline-color, var(--divider-color));
          background: var(--card-background-color);
          border-radius: var(--ha-border-radius-pill, 9999px);
          padding: 0;
          display: grid;
          place-items: center;
        }

        .todo-delete {
          min-width: 36px;
          min-height: 36px;
          line-height: 0;
          color: var(--secondary-text-color);
          border-color: transparent;
          background: transparent;
          border-radius: var(--ha-border-radius-pill, 9999px);
          padding: 0;
          display: grid;
          place-items: center;
        }

        .pending-pill {
          cursor: default;
          color: var(--secondary-text-color);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.05);
          border-style: dashed;
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
        }

        .todo-check:hover {
          color: var(--success-color, #43a047);
          border-color: rgba(var(--rgb-success-color, 67, 160, 71), 0.45);
          background: rgba(var(--rgb-success-color, 67, 160, 71), 0.1);
        }

        .todo-check.completing {
          color: var(--success-color, #43a047);
          border-color: rgba(var(--rgb-success-color, 67, 160, 71), 0.45);
          background: rgba(var(--rgb-success-color, 67, 160, 71), 0.14);
          animation: check-pop var(--ha-animation-duration-slow, 350ms) ease;
          pointer-events: none;
        }

        @keyframes check-pop {
          0% { transform: scale(1); }
          40% { transform: scale(1.3); }
          100% { transform: scale(1); }
        }

        .item-row.fade-out {
          animation: row-fade-out 400ms ease forwards;
          pointer-events: none;
        }

        @keyframes row-fade-out {
          0% { opacity: 1; transform: translateX(0); }
          100% { opacity: 0; transform: translateX(20px); }
        }

        .add-btn:hover,
        .chip:hover {
          border-color: var(--primary-color);
        }

        .todo-delete:hover {
          color: var(--primary-text-color);
          background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.04);
        }

        .add-row {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: var(--ha-space-2, 8px);
          align-items: start;
        }

        .add-field {
          position: relative;
        }

        #hf-item-input {
          box-sizing: border-box;
          width: 100%;
          min-height: var(--ha-space-11, 44px);
          border-radius: var(--ha-border-radius-lg, 12px);
          border: var(--ha-border-width-sm, 1px) solid var(--input-outlined-idle-border-color, var(--divider-color));
          background: var(--input-fill-color, var(--card-background-color));
          color: var(--input-ink-color, var(--primary-text-color));
          font: inherit;
          font-size: var(--ha-font-size-m, 0.875rem);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          transition: border-color var(--ha-animation-duration-fast, 150ms) ease-in-out,
                      box-shadow var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        #hf-item-input:hover {
          border-color: var(--input-outlined-hover-border-color, var(--outline-hover-color));
        }

        #hf-item-input:focus {
          outline: none;
          border-color: var(--primary-color);
          box-shadow: 0 0 0 1px var(--primary-color);
        }

        .add-btn {
          min-height: var(--ha-space-11, 44px);
          font-weight: var(--ha-font-weight-medium, 500);
          background: rgba(var(--rgb-primary-color, 0, 154, 199), 0.15);
          border-color: transparent;
          color: var(--primary-color);
        }

        .chips-wrap {
          display: flex;
          flex-wrap: wrap;
          gap: var(--ha-space-2, 8px);
        }

        .chip {
          background: var(--ha-assist-chip-filled-container-color, rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.15));
          border-color: transparent;
          font-weight: var(--ha-font-weight-medium, 500);
        }

        .empty,
        .empty-list {
          color: var(--secondary-text-color);
          font-style: italic;
          font-size: var(--ha-font-size-s, 0.75rem);
        }

        .error {
          border: var(--ha-border-width-sm, 1px) solid rgba(var(--rgb-error-color, 219, 68, 55), 0.4);
          color: var(--error-color, #db4437);
          background: rgba(var(--rgb-error-color, 219, 68, 55), 0.08);
          border-radius: var(--ha-border-radius-md, 8px);
          padding: var(--ha-space-2, 8px) var(--ha-space-3, 12px);
          font-size: var(--ha-font-size-s, 0.75rem);
        }

        .history-backdrop {
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.5);
          z-index: 999;
        }

        .history-modal {
          position: fixed;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          z-index: 1000;
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-border-radius-xl, 16px);
          box-shadow: var(--ha-box-shadow-l, 0 8px 12px rgba(0, 0, 0, 0.14));
          width: min(90vw, 380px);
          max-height: 80vh;
          display: grid;
          grid-template-rows: auto 1fr auto;
          overflow: hidden;
        }

        .history-modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: var(--ha-space-4, 16px);
          border-bottom: var(--ha-border-width-sm, 1px) solid var(--divider-color);
        }

        .history-modal-header h3 {
          margin: 0;
          font-size: var(--ha-font-size-l, 1rem);
          font-weight: var(--ha-font-weight-bold, 700);
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .history-modal-close {
          border: none;
          background: none;
          color: var(--secondary-text-color);
          cursor: pointer;
          padding: var(--ha-space-1, 4px);
          line-height: 0;
          border-radius: var(--ha-border-radius-pill, 9999px);
          transition: color var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .history-modal-close:hover {
          color: var(--primary-text-color);
        }

        .history-list {
          list-style: none;
          margin: 0;
          padding: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
          overflow-y: auto;
          display: grid;
          gap: var(--ha-space-1, 4px);
        }

        .history-entry {
          display: flex;
          align-items: center;
          gap: var(--ha-space-3, 12px);
          padding: var(--ha-space-2, 8px) 0;
          border-bottom: var(--ha-border-width-sm, 1px) solid rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.06);
        }

        .history-entry:last-child {
          border-bottom: none;
        }

        .history-icon {
          color: var(--success-color, #43a047);
          flex-shrink: 0;
          --mdc-icon-size: 20px;
        }

        .history-entry-content {
          display: grid;
          gap: 2px;
          min-width: 0;
        }

        .history-member {
          font-weight: var(--ha-font-weight-medium, 500);
          font-size: var(--ha-font-size-m, 0.875rem);
        }

        .history-time {
          color: var(--secondary-text-color);
          font-size: var(--ha-font-size-s, 0.75rem);
          letter-spacing: 0.4px;
        }

        .history-empty {
          color: var(--secondary-text-color);
          font-style: italic;
          font-size: var(--ha-font-size-s, 0.75rem);
          padding: 16px 0;
          text-align: center;
        }

        .history-modal-footer {
          padding: var(--ha-space-3, 12px) var(--ha-space-4, 16px);
          border-top: var(--ha-border-width-sm, 1px) solid var(--divider-color);
          display: flex;
          justify-content: flex-end;
        }

        .history-modal-close-btn {
          border: var(--ha-border-width-sm, 1px) solid var(--outline-color, var(--divider-color));
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: var(--ha-border-radius-pill, 9999px);
          padding: var(--ha-space-2, 8px) var(--ha-space-4, 16px);
          cursor: pointer;
          font: inherit;
          font-size: var(--ha-font-size-s, 0.75rem);
          font-weight: var(--ha-font-weight-medium, 500);
          transition: border-color var(--ha-animation-duration-fast, 150ms) ease-in-out;
        }

        .history-modal-close-btn:hover {
          border-color: var(--primary-color);
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
    this._editorReady = false;
  }

  setConfig(config) {
    this._config = {
      entity: "sensor.hass_flatmate_shopping_data",
      title: "Shopping List",
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
