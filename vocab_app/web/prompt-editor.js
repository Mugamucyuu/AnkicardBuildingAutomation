"use strict";

// A plain textarea preserves native selection, IME, clipboard and undo/redo.
// This controller never writes prompt contents into browser storage.
class PromptEditor {
  constructor({api, t, notify, onManifest}) {
    Object.assign(this, {api, t, notify, onManifest});
    this.nodes = Object.fromEntries([
      "prompt-type", "prompt-reader", "prompt-name", "prompt-text", "prompt-state",
      "prompt-current", "prompt-new", "prompt-save", "prompt-activate", "prompt-delete",
      "prompt-restore", "prompt-file", "upload-prompt-button", "prompt-stages", "prompt-stats"
    ].map(id => [id, document.getElementById(id)]));
    this.type = "";
    this.id = null;
    this.original = "";
    this.originalName = "";
    this.sha256 = null;
    this.ready = false;
    this.busy = false;
    this.isNew = false;
    this.request = 0;
    this.node("prompt-type").addEventListener("change", () => {
      const type = this.node("prompt-type").value;
      if (!this.discard()) { this.node("prompt-type").value = this.type; return; }
      this.type = type;
      this.id = null;
      this.isNew = false;
      this.render(this.manifest);
    });
    this.node("prompt-reader").addEventListener("change", () => {
      const id = this.node("prompt-reader").value;
      if (!this.discard()) { this.node("prompt-reader").value = this.id || ""; return; }
      this.isNew = false;
      this.load(id);
    });
    for (const id of ["prompt-name", "prompt-text"]) {
      this.node(id).addEventListener("input", () => this.update());
    }
    this.node("prompt-new").addEventListener("click", () => {
      if (!this.discard()) return;
      this.request++;
      this.id = null;
      this.isNew = true;
      this.ready = true;
      this.original = this.originalName = "";
      this.sha256 = null;
      this.node("prompt-name").value = "my-" + this.type + ".md";
      this.node("prompt-text").value = "";
      this.render(this.manifest);
      this.node("prompt-text").focus();
    });
    this.node("prompt-save").addEventListener("click", () => this.save(false));
    this.node("prompt-activate").addEventListener("click", () => this.save(true));
    this.node("prompt-delete").addEventListener("click", () => this.remove());
    this.node("prompt-restore").addEventListener("click", () => this.restore());
    this.node("prompt-file").addEventListener("change", event => this.importFile(event));
    this.node("prompt-text").addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (!this.node("prompt-save").disabled) this.save(false);
      }
    });
    window.addEventListener("beforeunload", event => {
      if (this.dirty() || this.busy) { event.preventDefault(); event.returnValue = ""; }
    });
  }

  node(id) { return this.nodes[id]; }
  editable() { return !["legacy", "unclassified"].includes(this.type); }
  dirty() {
    return this.ready && (this.node("prompt-text").value !== this.original ||
      this.node("prompt-name").value !== this.originalName);
  }
  discard() { return !this.busy && (!this.dirty() || window.confirm(this.t("discardPrompt"))); }
  label(type) { return this.t(type === "generation" ? "generationStage" : type + "Stage"); }
  file(id) { return this.manifest?.files.find(file => file.id === id && file.type === this.type); }
  activeId() { return this.manifest.bindings[this.type] || (this.manifest.stages[this.type] ? "builtin/" + this.manifest.stages[this.type] : null); }
  fileLabel(file) {
    return (file.builtin ? this.t("builtinPrompt") : this.t("customPrompt")) + " · " +
      (file.display_name || file.name) + (file.builtin ? "" : " · " + file.id.split("/")[1].slice(0, 8));
  }

  render(manifest, selectedId) {
    this.manifest = manifest;
    const types = manifest.types.filter(type => !["legacy", "unclassified"].includes(type) || manifest.files.some(f => f.type === type));
    if (!types.includes(this.type)) { this.type = types[0]; this.id = null; this.isNew = false; }
    this.node("prompt-type").replaceChildren(...types.map(type => new Option(this.label(type), type)));
    this.node("prompt-type").value = this.type;
    const files = manifest.files.filter(file => file.type === this.type);
    this.node("prompt-reader").replaceChildren(...files.map(file => new Option(this.fileLabel(file), file.id)));
    if (this.isNew) this.node("prompt-reader").prepend(new Option(this.t("newDraft"), ""));
    const id = selectedId || (files.some(f => f.id === this.id) ? this.id : this.activeId() || files[0]?.id);
    this.node("prompt-reader").value = this.isNew ? "" : id || "";
    const active = this.file(this.activeId());
    this.node("prompt-current").textContent = active ? this.t("activePrompt") + " " + this.fileLabel(active) : this.t("supplementSelectHint");
    this.node("prompt-stages").hidden = !manifest.stages[this.type];
    if (!this.isNew && (this.id !== id || !this.ready)) this.load(id);
    this.update();
  }

  async load(id) {
    const request = ++this.request;
    this.id = id || null;
    this.ready = false;
    this.original = this.originalName = "";
    this.node("prompt-text").value = "";
    this.node("prompt-name").value = "";
    this.update();
    if (!id) return;
    try {
      const result = await this.api("/api/prompt?id=" + encodeURIComponent(id) + "&type=" + encodeURIComponent(this.type));
      if (request !== this.request) return;
      this.original = result.text;
      this.originalName = this.file(id)?.display_name || this.file(id)?.name || "prompt.md";
      this.sha256 = result.sha256;
      this.node("prompt-text").value = this.original;
      this.node("prompt-name").value = this.originalName;
      this.ready = true;
    } catch (error) { if (request === this.request) this.notify(error.message, true); }
    finally { if (request === this.request) this.update(); }
  }

  update() {
    const dirty = this.dirty(), editable = this.editable(), file = this.file(this.id);
    document.documentElement.dataset.promptDirty = String(dirty || this.busy);
    this.node("prompt-type").disabled = this.busy;
    this.node("prompt-reader").disabled = this.busy || !this.node("prompt-reader").options.length;
    this.node("prompt-name").readOnly = this.busy || !editable || !this.ready;
    this.node("prompt-text").readOnly = this.busy || !editable || !this.ready;
    this.node("prompt-new").disabled = this.busy || !editable;
    this.node("prompt-file").disabled = this.busy || !editable;
    this.node("upload-prompt-button").hidden = !editable;
    const nonempty = this.ready && this.node("prompt-text").value.trim();
    this.node("prompt-save").disabled = this.busy || !editable || !nonempty || (!dirty && !file?.builtin);
    this.node("prompt-activate").hidden = !this.manifest?.stages[this.type];
    this.node("prompt-activate").disabled = this.busy || !nonempty || (!dirty && this.id === this.activeId());
    this.node("prompt-activate").textContent = this.t(dirty || this.isNew ? "saveAndActivate" : "activatePrompt");
    this.node("prompt-delete").disabled = this.busy || !this.ready || !file || file.builtin;
    this.node("prompt-restore").disabled = this.busy || !this.manifest?.bindings[this.type];
    this.node("prompt-state").textContent = this.t(this.busy ? "promptWorking" : dirty ? "promptUnsaved" : !this.ready ? (this.id ? "promptLoading" : "emptyPromptType") : file?.builtin ? "builtinEditHint" : this.isNew ? "newDraft" : "promptSaved");
    this.node("prompt-state").classList.toggle("unsaved", Boolean(dirty));
    const text = this.node("prompt-text").value;
    this.node("prompt-stats").textContent = (text ? text.split("\n").length : 0) + " " + this.t("promptLines") + " · " + [...text].length + " " + this.t("promptCharacters");
  }

  async save(activate) {
    if (this.busy || !this.ready) return;
    this.busy = true;
    this.update();
    try {
      if (activate && !this.dirty() && this.id) {
        this.onManifest(await this.api("/api/prompts/bind", {stage:this.type, file:this.id}));
      } else {
        const result = await this.api("/api/prompts/save", {name:this.node("prompt-name").value.trim(),
          text:this.node("prompt-text").value, type:this.type, source:this.id,
          sha256:this.sha256, activate});
        this.id = result.id;
        this.original = result.text;
        this.originalName = this.node("prompt-name").value.trim();
        this.node("prompt-name").value = this.originalName;
        this.sha256 = result.sha256;
        this.isNew = false;
        this.onManifest(result.manifest);
      }
      this.notify(this.t(activate ? "promptActivated" : this.type === "supplement" ? "promptSupplementSaved" : "promptVersionSaved"));
    } catch (error) { this.notify(error.message, true); }
    finally { this.busy = false; this.update(); }
  }

  async restore() {
    if (this.busy) return;
    this.busy = true;
    this.update();
    try {
      this.onManifest(await this.api("/api/prompts/bind", {stage:this.type, file:null}));
      this.notify(this.t("promptRestored"));
    } catch (error) { this.notify(error.message, true); }
    finally { this.busy = false; this.update(); }
  }

  async remove() {
    if (this.busy || !this.id || this.file(this.id)?.builtin) return;
    const name = this.fileLabel(this.file(this.id));
    const active = Object.values(this.manifest.bindings).includes(this.id);
    if (!window.confirm(this.t(active ? "deleteActivePrompt" : "deletePromptConfirm") + "\n\n" + name + (this.dirty() ? "\n\n" + this.t("discardPrompt") : ""))) return;
    this.busy = true;
    this.update();
    try {
      const result = await this.api("/api/prompts/delete", {id:this.id, sha256:this.sha256});
      this.id = null;
      this.ready = false;
      this.isNew = false;
      this.onManifest(result.manifest);
      this.notify(this.t("promptDeleted"));
    } catch (error) { this.notify(error.message, true); }
    finally { this.busy = false; this.update(); }
  }

  async importFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!this.discard()) { event.target.value = ""; return; }
    this.busy = true;
    this.update();
    try {
      if (file.size > 256000 || !/\.(txt|md)$/i.test(file.name)) throw new Error(this.t("fileTooLarge"));
      const text = new TextDecoder("utf-8", {fatal:true}).decode(await file.arrayBuffer()).replace(/^\uFEFF/, "");
      const result = await this.api("/api/prompts/upload", {name:file.name, text, type:this.type});
      this.id = result.id;
      this.ready = false;
      this.isNew = false;
      this.onManifest(result.manifest);
      this.notify(this.t(this.type === "supplement" ? "promptSupplementSaved" : "promptImported"));
    } catch (error) { this.notify(error.message, true); }
    finally { event.target.value = ""; this.busy = false; this.update(); }
  }
}
