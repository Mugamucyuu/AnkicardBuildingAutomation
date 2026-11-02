# Prompt inventory and transparency

Every authored model instruction is file-backed. UI Prompt management keeps each type separate and supports direct text editing, new prompts, TXT/MD import, versioned saves, explicit activation, deletion of custom versions and restore. `validation.txt` contains JSON inside a text file so it uses the same editing/versioning workflow.

## Editing in the application

1. Open **Prompts**, choose a type, then a file/version. Selecting a file opens it for editing; it does not change the active prompt.
2. Type, select, copy/paste and undo/redo as in a normal text field. **Save version** or **Ctrl+S / Cmd+S** saves a custom version without changing defaults. Editing a built-in creates a custom version; the shipped original stays available.
3. Choose **Use for new tasks**, or **Save & use for new tasks** when the editor has changes, to activate that version. The current active version is shown above the editor. Supplements are selected per batch on the import page instead.
4. **New prompt** creates a blank draft in the chosen category. **Import file** accepts UTF-8 TXT/MD, up to 256,000 bytes, and opens the imported file immediately. Imports are not activated automatically.
5. **Delete version** removes the selected custom file after confirmation. Deleting an active custom version restores the built-in for its stage. Older custom versions remain available until explicitly deleted. Built-in files cannot be deleted.

Unsaved drafts stay in the editor when visiting other app pages or changing the UI language. Switching files/categories or importing another file asks before discarding changes. Browser reload/close and desktop exit warn about unsaved changes; drafts are not autosaved or restored after a crash. Saves retain immutable, content-addressed versions (identical filename/type/content reuses the same version). A hash check prevents a stale editor from saving over or deleting a file changed outside the application. Renaming the file before saving creates a separately named version.

Saving validation rules checks their JSON structure before writing. Assembled instructions always show **active saved** prompts, not unsaved drafts. Existing and running jobs retain their own prompt snapshots even if the source custom file is later edited or deleted. Historical/uncategorized legacy files remain readable; import them into a supported category to edit/use them.

| Type | Used when |
| --- | --- |
| `generation` | Main JSON/content instructions for every word |
| `style_en`, `style_ja`, `style_ko` | Exactly one language-specific teaching style |
| `tag_policy` | Shared by generation and tag auditing |
| `image_plan` | Appended only when images are enabled |
| `search_planner` | A separate model request in web-search mode |
| `tag_review` | Separate tag audit after live content generation |
| `content_repair` | Wrapper around content/JSON/citation feedback on retry |
| `tag_repair` | Wrapper around tag validation feedback on retry |
| `validation` | Editable content checks plus all 26 authored validation-message templates |
| `supplement` | Optional batch-specific text appended to the generation component |

The default generation assembly is `generation + tag_policy + language style + optional image_plan`, separated by two newlines. A selected supplement is already appended to the generation component. Tag audit is `tag_review + tag_policy`. Search, audit and repair stages remain separate because they have different input/output contracts. Some deliberate repetition between content and language instructions is retained: removing it would change existing requests and could shift the teaching style.

## Editable content validation

The JSON rules configure minimum examples per language (1–20), explanation-language checks, Japanese reading/form checks, prose emphasis and its maximum ratio, paragraph checks, and collocation checks/minimum explanation length. Collocation checks include its object format and bold phrase. Change the corresponding style prompt too if you want the model to request fewer examples or less bold; the validator no longer secretly forces the old minimum after you change its rules.

`messages` exposes all authored content and tag-audit feedback. `{v0}`, `{v1}` insert the relevant field/index/count. Repair templates use `{issues}` to insert these messages. Keep placeholders when replacing text. Default texts and thresholds match the pre-refactor behavior.

## Technical constraints

Valid JSON, required field types/nonempty values, at least one example, valid citation IDs, valid tags, mandatory POS and Japanese/Korean origin, and safe media paths remain enforced by the application. They are not optional teaching preferences. Technical exceptions may contribute dynamic error data to a repair request; the complete emitted request is available in task records. Editing natural-language instructions does not change the program's data contract.

## Full visibility

- **Assembled instructions** shows the currently selected generation/audit/search/repair components, validation configuration and a sample input. It performs no model or website calls. It uses the starter tags and empty research; it is not a claim to show a future search result.
- **Actual model requests** on each task word shows the batch's exact template snapshot and every JSON request sent to the provider, including real allowed tags, source excerpts, supplemental text and repair attempts. HTTP authentication headers/API keys are not recorded. Failed requests are recorded before sending.
- Older jobs may have template snapshots only. Missing traces are explicitly identified; records are never retroactively invented.
- CLI live requests are recorded under the selected preview directory's `requests/` folder.

The application does not read old card bodies as teaching-style examples and does not inherit the assistant conversation. A fresh collection uses the shipped catalog/style files. User state and request records are private local data, excluded from source releases. Provider-internal behavior is outside this application's prompt control.
