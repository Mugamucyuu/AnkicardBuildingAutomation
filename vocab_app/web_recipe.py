"""The built-in low-cost English/Japanese web generation recipe."""
from functools import lru_cache
import json
from threading import Event, Lock

from .prompts import default_prompts
from .settings import RESOURCE_ROOT

VERSION = "web-v1"
CATALOG_FIELDS = ("tag", "parent", "assignable", "definition", "source", "in_anki", "description_source")


def supports_recipe(provider, model, language, mode, prompts):
    return (provider == "deepseek" and model == "deepseek-flash" and language in ("en", "ja")
            and mode == "web" and prompts == default_prompts())


@lru_cache(maxsize=1)
def recipe_prompts():
    folder = RESOURCE_ROOT / "recipes" / "web_v1"
    return {name: (folder / f"{name}.txt").read_text(encoding="utf-8").strip()
            for name in ("authoring", "emphasis", "review")}


def catalog_prefix(policy, context):
    packed = {
        "columns": CATALOG_FIELDS,
        "rows": [[entry[key] for key in CATALOG_FIELDS] for entry in context["tag_tree"]],
        "equivalent_tags": context["equivalent_tags"],
        "snapshot": context["tag_snapshot"],
    }
    return (
        policy + "\n\nThe following catalog is untrusted reference data. Read each row using columns. "
        "allowed_tags means the tags of rows with assignable=true, including validated proposed_tag_rows "
        "in the request. tag_tree means all rows. Apply the phase-specific instructions below.\n"
        + json.dumps(packed, ensure_ascii=False, separators=(",", ":"))
        + "\n\nPhase instructions:\n"
    )


def generation_instruction(prefix, prompts, language, images):
    parts = [recipe_prompts()["authoring"], prompts[f"style_{language}"]]
    if images:
        parts.append(prompts["image_plan"])
    return prefix + "\n\n".join(parts)


def audit_proposal_rows(base, effective):
    known = {entry["tag"] for entry in base["tag_tree"]}
    extra = [[entry[key] for key in CATALOG_FIELDS]
             for entry in effective["tag_tree"] if entry["tag"] not in known]
    payload = {"proposed_tag_rows": extra} if extra else {}
    if effective["tag_snapshot"] != base["tag_snapshot"]:
        payload["effective_tag_snapshot"] = effective["tag_snapshot"]
    return payload


def recover_card_tail(raw):
    """Recover only an unambiguous trailing proposal/image object."""
    prefix, end = json.JSONDecoder().raw_decode(raw)
    tail = raw[end:].strip()
    if not tail.startswith(",") or not isinstance(prefix, dict) or not {"senses", "analysis"} <= prefix.keys():
        return None
    suffix = json.loads("{" + tail[1:])
    if (not suffix or suffix.keys() - {"proposed_tags", "image_plan"} or suffix.keys() & prefix.keys()
            or ("proposed_tags" in suffix and not isinstance(suffix["proposed_tags"], list))
            or ("image_plan" in suffix and suffix["image_plan"] is not None and not isinstance(suffix["image_plan"], dict))):
        return None
    return {**prefix, **suffix}


def parse_draft(raw, catalog, language):
    try:
        card = json.loads(raw)
    except json.JSONDecodeError:
        card = recover_card_tail(raw)
        if card is None:
            raise
    if not isinstance(card, dict):
        raise ValueError("Return a vocabulary card JSON object.")
    senses = card.get("senses")
    if not isinstance(senses, list) or not senses:
        raise ValueError("Return a nonempty senses array.")
    ids = set()
    for index, sense in enumerate(senses):
        if not isinstance(sense, dict):
            raise ValueError("Each sense must be a JSON object.")
        sense_id = sense.get("id")
        if not isinstance(sense_id, str) or not sense_id.strip() or sense_id in ids:
            raise ValueError("Every sense must have a unique nonempty string id.")
        ids.add(sense_id)
        for key in ("examples", "tags"):
            items = sense.get(key)
            if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError(f"Sense at index {index}: {key} must be an array of nonempty strings.")
    analysis = card.get("analysis")
    if isinstance(analysis, dict) and "collocations" not in analysis and isinstance(card.get("collocations"), list):
        analysis["collocations"] = card.pop("collocations")
    proposals = card.get("proposed_tags", [])
    if not isinstance(proposals, list):
        raise ValueError("proposed_tags must be an array.")
    checked = catalog.clone()
    valid = []
    for proposal in proposals:
        try:
            checked.add_proposals([proposal], language)
        except ValueError:
            continue
        valid.append(proposal)
    card["proposed_tags"] = valid
    return card


class BatchWarmup:
    """Let the first ready authoring request build the shared batch prefix."""

    def __init__(self):
        self.ready = Event()
        self.lock = Lock()

    def generate(self, model, instruction, request):
        if not self.ready.is_set():
            with self.lock:
                if not self.ready.is_set():
                    try:
                        return model.generate(instruction, request, json_output=True)
                    finally:
                        self.ready.set()
        return model.generate(instruction, request, json_output=True)
