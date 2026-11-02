# Image selection

The model supplies a sense-specific plan in the editable `image_plan` prompt. Plans distinguish photos from diagrams and can include alternative queries and distracting scenes. Public image retrieval and ranking do not invoke a vision model.

The selector merges article images and up to three Commons searches, deduplicates candidates and sorts the entire pool. Rankings consider exact subject/context phrases, credits/license, dimensions, scene distractors, diagram format, explicit filename language codes and specialized subtopics. Only approved candidates are eligible for download fallback. SVGs use publisher raster thumbnails, not executable inline SVG.

API calls are paced, temporary errors are retried within a bound, and Retry-After is respected; a long requested delay ends that attempt rather than being shortened. Complete retrieval failure is reported separately from a lack of matching candidates.

Run `python tools/test_image_selection_live.py` for the 20-word public-network regression. It uses fixed sense plans, not generated explanations, and does not call paid models or write to Anki. Results and the gallery go to `output/image-selection-20-20261101/`. Successful downloads are not semantic acceptance tests: metadata cannot reliably identify a close-up, an obscured subject or a diagram that is too complex. Human review or a future optional vision stage remains necessary.
