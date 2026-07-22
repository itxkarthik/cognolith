import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroundingValidation:
    is_valid: bool
    reason: str | None = None


def validate_grounded_answer(answer: str, *, valid_citation_ids: set[int]) -> GroundingValidation:
    if not valid_citation_ids:
        return GroundingValidation(True)
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
    if cited - valid_citation_ids:
        return GroundingValidation(False, "unknown_citations")
    if not cited:
        return GroundingValidation(False, "missing_citations")
    return GroundingValidation(True)


def build_grounding_repair_messages(
    *, messages: list[dict[str, str]], draft: str, valid_citation_ids: set[int]
) -> list[dict[str, str]]:
    valid = ", ".join(f"[{item}]" for item in sorted(valid_citation_ids))
    instruction = (
        "Rewrite the draft so every workspace-derived factual claim uses only these citations: "
        f"{valid}. Preserve all supported details and do not mention this correction.\n\nDRAFT:\n{draft}"
    )
    return [
        *messages,
        {"role": "assistant", "content": draft},
        {"role": "user", "content": instruction},
    ]
