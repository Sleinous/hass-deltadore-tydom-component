const GUIDE_EVENT = "deltadore_tydom_association_guide";
const DIALOG_TAG = "deltadore-association-guide-dialog";

class DeltaDoreAssociationGuideDialog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._close = this._close.bind(this);
  }

  connectedCallback() {
    this._render();
  }

  showGuide({ title, instructions, illustrations }) {
    this._title = title;
    this._instructions = instructions;
    this._illustrations = illustrations;
    this._render();
    this.shadowRoot.querySelector(".backdrop")?.classList.add("visible");
    this.shadowRoot.querySelector(".dialog")?.focus();
  }

  _close() {
    this.shadowRoot.querySelector(".backdrop")?.classList.remove("visible");
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }
    this.shadowRoot.innerHTML = `
      <style>
        :host { font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
        .backdrop {
          align-items: center; background: rgba(0, 0, 0, .55); display: none;
          inset: 0; justify-content: center; padding: 16px; position: fixed;
          z-index: 10000;
        }
        .backdrop.visible { display: flex; }
        .dialog {
          background: var(--card-background-color, #fff); border-radius: 16px;
          box-shadow: 0 12px 36px rgba(0, 0, 0, .35); color: var(--primary-text-color, #212121);
          max-height: calc(100vh - 32px); max-width: 760px; outline: none; overflow: auto;
          width: 100%;
        }
        header {
          align-items: center; border-bottom: 1px solid var(--divider-color, #ddd);
          display: flex; gap: 12px; justify-content: space-between; padding: 20px 24px;
        }
        h2 { font-size: 22px; line-height: 1.25; margin: 0; }
        button {
          background: transparent; border: 0; border-radius: 50%; color: inherit;
          cursor: pointer; font-size: 28px; height: 40px; line-height: 1; width: 40px;
        }
        button:hover { background: var(--secondary-background-color, #eee); }
        main { padding: 20px 24px 28px; }
        ol { margin: 0; padding-left: 24px; }
        li { line-height: 1.45; margin: 0 0 14px; white-space: pre-line; }
        h3 { font-size: 18px; margin: 28px 0 14px; }
        figure { margin: 0 0 20px; text-align: center; }
        img { display: block; height: auto; margin: 0 auto; max-width: 100%; }
        figcaption { color: var(--secondary-text-color, #666); font-size: 13px; margin-top: 6px; }
      </style>
      <div class="backdrop" role="presentation">
        <section class="dialog" role="dialog" aria-modal="true" aria-labelledby="guide-title" tabindex="-1">
          <header>
            <h2 id="guide-title"></h2>
            <button type="button" aria-label="Fermer">×</button>
          </header>
          <main>
            <ol class="instructions"></ol>
            <section class="illustrations" hidden>
              <h3>Illustrations officielles</h3>
              <div class="images"></div>
            </section>
          </main>
        </section>
      </div>
    `;

    const backdrop = this.shadowRoot.querySelector(".backdrop");
    const dialog = this.shadowRoot.querySelector(".dialog");
    const closeButton = this.shadowRoot.querySelector("button");
    closeButton.addEventListener("click", this._close);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) this._close();
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this._close();
    });

    this.shadowRoot.querySelector("#guide-title").textContent = this._title || "Guide d'association";
    const instructionList = this.shadowRoot.querySelector(".instructions");
    (this._instructions || []).forEach((instruction) => {
      const item = document.createElement("li");
      item.textContent = instruction.replace(/^\d+\.\s*/, "");
      instructionList.append(item);
    });

    if (this._illustrations?.length) {
      const section = this.shadowRoot.querySelector(".illustrations");
      const images = this.shadowRoot.querySelector(".images");
      section.hidden = false;
      this._illustrations.forEach((source, index) => {
        const figure = document.createElement("figure");
        const image = document.createElement("img");
        image.src = source;
        image.alt = `Illustration officielle de l'étape ${index + 1}`;
        const caption = document.createElement("figcaption");
        caption.textContent = `Étape ${index + 1}`;
        figure.append(image, caption);
        images.append(figure);
      });
    }
  }
}

const getDialog = () => {
  let dialog = document.querySelector(DIALOG_TAG);
  if (!dialog) {
    dialog = document.createElement(DIALOG_TAG);
    document.body.append(dialog);
  }
  return dialog;
};

const subscribe = async () => {
  const hass = document.querySelector("home-assistant")?.hass;
  if (!hass?.connection) {
    window.setTimeout(subscribe, 500);
    return;
  }
  await hass.connection.subscribeEvents(
    (event) => getDialog().showGuide(event.data),
    GUIDE_EVENT,
  );
};

if (!customElements.get(DIALOG_TAG)) {
  customElements.define(DIALOG_TAG, DeltaDoreAssociationGuideDialog);
  subscribe();
}
