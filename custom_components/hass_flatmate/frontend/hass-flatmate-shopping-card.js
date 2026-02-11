class HassFlatmateShoppingCard extends HTMLElement {
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
    if (!this._root) {
      this._root = document.createElement("div");
      this.appendChild(this._root);
    }
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
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
      addFavorite: attributes.service_add_favorite || "hass_flatmate_add_favorite_item",
      deleteFavorite: attributes.service_delete_favorite || "hass_flatmate_delete_favorite_item",
    };
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

  async _addFavorite(name) {
    const normalized = String(name || "").trim();
    if (!normalized) {
      return;
    }

    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.addFavorite, { name: normalized });
    } catch (error) {
      this._errorMessage = error?.message || "Unable to add favorite";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _deleteFavorite(id) {
    if (!id) {
      return;
    }

    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.deleteFavorite, { favorite_id: id });
    } catch (error) {
      this._errorMessage = error?.message || "Unable to delete favorite";
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
      this._errorMessage = error?.message || "Unable to complete item";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _deleteItem(id) {
    if (!id) {
      return;
    }

    this._busy = true;
    this._errorMessage = "";
    this._render();
    try {
      const meta = this._serviceMeta(this._stateObj.attributes || {});
      await this._callService(meta.deleteItem, { item_id: id });
    } catch (error) {
      this._errorMessage = error?.message || "Unable to delete item";
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _bindEvents() {
    const form = this._root.querySelector("#hass-flatmate-add-form");
    const input = this._root.querySelector("#hass-flatmate-item-input");
    const favoriteButton = this._root.querySelector("#hass-flatmate-add-favorite");

    if (input) {
      input.addEventListener("input", (event) => {
        this._draftName = event.target.value;
      });
    }

    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await this._addItem(this._draftName);
      });
    }

    if (favoriteButton) {
      favoriteButton.addEventListener("click", async () => {
        await this._addFavorite(this._draftName);
      });
    }

    this._root.querySelectorAll("[data-action='add-quick']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._addItem(el.dataset.name);
      });
    });

    this._root.querySelectorAll("[data-action='delete-favorite']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._deleteFavorite(Number(el.dataset.favoriteId));
      });
    });

    this._root.querySelectorAll("[data-action='complete-item']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._completeItem(Number(el.dataset.itemId));
      });
    });

    this._root.querySelectorAll("[data-action='delete-item']").forEach((el) => {
      el.addEventListener("click", async () => {
        await this._deleteItem(Number(el.dataset.itemId));
      });
    });
  }

  _render() {
    if (!this._config || !this._root || !this._hass) {
      return;
    }

    this._stateObj = this._hass.states[this._config.entity];
    if (!this._stateObj) {
      this._root.innerHTML = `
        <ha-card>
          <div class="hass-flatmate-shopping-empty">
            Entity not found: <code>${this._escape(this._config.entity)}</code>
          </div>
        </ha-card>
      `;
      return;
    }

    const attrs = this._stateObj.attributes || {};
    const openItems = Array.isArray(attrs.open_items) ? attrs.open_items : [];
    const favorites = Array.isArray(attrs.favorites) ? attrs.favorites : [];
    const recents = Array.isArray(attrs.recents) ? attrs.recents : [];
    const openCount = Number.parseInt(this._stateObj.state, 10) || openItems.length;

    const favoriteChips = favorites
      .map((item) => {
        const id = Number(item.id);
        const name = this._escape(item.name);
        return `
          <div class="chip-row">
            <button class="chip" type="button" data-action="add-quick" data-name="${name}">${name}</button>
            <button class="chip-delete" type="button" data-action="delete-favorite" data-favorite-id="${id}" title="Remove favorite">✕</button>
          </div>
        `;
      })
      .join("");

    const recentChips = recents
      .slice(0, 12)
      .map((name) => {
        const escaped = this._escape(name);
        return `<button class="chip" type="button" data-action="add-quick" data-name="${escaped}">${escaped}</button>`;
      })
      .join("");

    const itemRows = openItems
      .map((item) => {
        const id = Number(item.id);
        const name = this._escape(item.name);
        const age = Number(item.age_days);
        const ageLabel = Number.isFinite(age) ? `${age}d` : "";
        const addedBy = item.added_by_name ? this._escape(item.added_by_name) : "";
        return `
          <li class="item-row">
            <div class="item-main">
              <div class="item-name">${name}</div>
              <div class="item-meta">${ageLabel}${addedBy ? ` · by ${addedBy}` : ""}</div>
            </div>
            <div class="item-actions">
              <button class="action action-complete" type="button" data-action="complete-item" data-item-id="${id}">Done</button>
              <button class="action action-delete" type="button" data-action="delete-item" data-item-id="${id}">Delete</button>
            </div>
          </li>
        `;
      })
      .join("");

    const draftName = this._escape(this._draftName || "");
    const disabledAttr = this._busy ? "disabled" : "";
    const errorMessage = this._errorMessage ? this._escape(this._errorMessage) : "";

    this._root.innerHTML = `
      <ha-card>
        <div class="hass-flatmate-shopping-card">
          <div class="header-row">
            <div>
              <h2>${this._escape(this._config.title)}</h2>
              <p>${openCount} open items</p>
            </div>
          </div>

          <form id="hass-flatmate-add-form" class="add-row">
            <input
              id="hass-flatmate-item-input"
              type="text"
              placeholder="Add item"
              value="${draftName}"
              autocomplete="off"
              ${disabledAttr}
            />
            <button class="primary" type="submit" ${disabledAttr}>Add</button>
            <button id="hass-flatmate-add-favorite" class="secondary" type="button" ${disabledAttr}>Favorite</button>
          </form>

          ${errorMessage ? `<div class="error-banner">${errorMessage}</div>` : ""}

          <section>
            <h3>Favorites</h3>
            <div class="chips-wrap">
              ${favoriteChips || '<span class="empty">No favorites yet</span>'}
            </div>
          </section>

          <section>
            <h3>Recent</h3>
            <div class="chips-wrap">
              ${recentChips || '<span class="empty">No recent items yet</span>'}
            </div>
          </section>

          <section>
            <h3>Open items</h3>
            <ul class="item-list">
              ${itemRows || '<li class="empty-list">Shopping list is empty</li>'}
            </ul>
          </section>
        </div>
      </ha-card>

      <style>
        .hass-flatmate-shopping-card {
          padding: 16px;
          display: grid;
          gap: 14px;
        }

        .header-row {
          display: flex;
          align-items: start;
          justify-content: space-between;
        }

        .header-row h2 {
          margin: 0;
          font-size: 1.2rem;
          line-height: 1.3;
        }

        .header-row p {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
          font-size: 0.9rem;
        }

        .add-row {
          display: grid;
          grid-template-columns: 1fr auto auto;
          gap: 8px;
          align-items: center;
        }

        #hass-flatmate-item-input {
          box-sizing: border-box;
          width: 100%;
          min-height: 42px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          padding: 10px 12px;
        }

        #hass-flatmate-item-input:focus {
          outline: none;
          border-color: var(--primary-color);
          box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 55%, transparent);
        }

        section h3 {
          margin: 0 0 8px;
          font-size: 0.95rem;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .chips-wrap {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .chip-row {
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }

        .chip,
        .chip-delete,
        .action,
        .primary,
        .secondary {
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border-radius: 12px;
          padding: 6px 10px;
          cursor: pointer;
          font: inherit;
        }

        .chip:hover,
        .chip-delete:hover,
        .action:hover,
        .primary:hover,
        .secondary:hover {
          border-color: var(--primary-color);
        }

        .chip-delete {
          padding: 6px 8px;
          border-radius: 10px;
        }

        .primary {
          background: color-mix(in srgb, var(--primary-color) 18%, var(--card-background-color));
        }

        .secondary {
          background: color-mix(in srgb, var(--info-color, var(--primary-color)) 15%, var(--card-background-color));
        }

        .item-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: grid;
          gap: 8px;
        }

        .item-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding: 10px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
        }

        .item-main {
          min-width: 0;
        }

        .item-name {
          font-weight: 600;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .item-meta {
          margin-top: 2px;
          color: var(--secondary-text-color);
          font-size: 0.82rem;
        }

        .item-actions {
          display: inline-flex;
          gap: 6px;
          flex-shrink: 0;
        }

        .action-complete {
          background: color-mix(in srgb, var(--success-color, #4caf50) 16%, var(--card-background-color));
        }

        .action-delete {
          background: color-mix(in srgb, var(--error-color, #f44336) 14%, var(--card-background-color));
        }

        .empty,
        .empty-list,
        .hass-flatmate-shopping-empty {
          color: var(--secondary-text-color);
          font-style: italic;
        }

        .error-banner {
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

          .item-row {
            flex-direction: column;
            align-items: flex-start;
          }

          .item-actions {
            width: 100%;
          }

          .action {
            flex: 1;
          }
        }
      </style>
    `;

    this._bindEvents();
  }
}

if (!customElements.get("hass-flatmate-shopping-card")) {
  customElements.define("hass-flatmate-shopping-card", HassFlatmateShoppingCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "hass-flatmate-shopping-card")) {
  window.customCards.push({
    type: "hass-flatmate-shopping-card",
    name: "Hass Flatmate Shopping Card",
    description: "Manage the hass_flatmate shopping list with quick add, favorites, and completion actions.",
    preview: true,
  });
}
