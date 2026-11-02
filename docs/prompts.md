# Prompt inventory and transparency

Every authored model instruction is file-backed. UI Prompt management keeps each type separate and supports TXT/MD upload, replacement, read-only inspection and restore. `validation.txt` contains JSON inside a text file so it uses the same upload/versioning workflow.

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
