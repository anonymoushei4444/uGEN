import logging

# Curated retrieval queries per (model_family, attack_vector).
# Family detection mirrors the substring logic in tools/retriever_llm.py.

_QUERIES: dict[str, dict[str, list[str]]] = {
    "claude": {
        "Spectre-v1": [
            "Controlled Branch Mispredictor",
            "Controlled Delay",
            "Stride Masking",
            "Measuring Memory Access Time",
            "Array Initialization",
        ],
        "Prime-Probe": [
            "Randomized Pointer-Chase Linked List Construction",
            "Probe and High-Resolution Timing",
            "Victim Memory Access",
        ],
    },
    "gpt": {
        "Spectre-v1": [
            # Original: ["Controlled Branch Mispredictor", "Cache Eviction", "Controlled Delay",
            #            "Measuring Memory Access Time", "Stride Masking", "Score Accumulation",
            #            "Array Initialization"]
            "Controlled Branch Mispredictor",
            "Cache Eviction",
            "Controlled Delay",
            "Branch Predictor Training Loop",
            "Measuring Memory Access Time",
            "Stride Masking",
            "Score Accumulation",
            "Array Initialization",
        ],
        "Prime-Probe": [
            "Eviction Set Construction",
            "Randomized Pointer-Chase Linked List Construction",
            "Probe and High-Resolution Timing",
            "Victim Memory Access",
        ],
    },
    "qwen3": {
        "Spectre-v1": [
            # Original: ["Controlled Branch Mispredictor", "Controlled Delay",
            #            "Probe and High-Resolution Timing", "Mixed Probe order",
            #            "Score Accumulation", "Array Initialization"]
            "Secret reachability",
            "Controlled Branch Mispredictor",
            "Branch Predictor Training Loop",
            "Cache Eviction",
            "Mixed Probe order",
            "Hit/Miss Classification Threshold",
            "Score Accumulation",
            "Array Initialization",
        ],
        "Prime-Probe": [
            "Randomized Pointer-Chase Linked List Construction",
            "Probe and High-Resolution Timing",
            "Victim Memory Access",
        ],
    },
}


def _get_model_family(model_key: str) -> str | None:
    key = model_key.lower()
    if "claude" in key or "anthropic" in key:
        return "claude"
    if "gpt" in key or "openai" in key or "4o" in key:
        return "gpt"
    if "qwen3" in key or "qwen" in key:
        return "qwen3"
    return None


def get_retrieval_questions(model_key: str, attack_vector: str) -> list[str]:
    log = logging.getLogger(__name__)
    family = _get_model_family(model_key)

    if family is None:
        log.error(
            f"No curated retrieval questions for model '{model_key}' "
            f"(attack: '{attack_vector}'). RAG retrieval will be skipped. "
            f"Add an entry to app/retrieval_queries.py to enable it."
        )
        return []

    questions = _QUERIES.get(family, {}).get(attack_vector)
    if questions is None:
        log.error(
            f"No curated retrieval questions for family='{family}', "
            f"attack='{attack_vector}'. RAG retrieval will be skipped. "
            f"Add an entry to app/retrieval_queries.py to enable it."
        )
        return []

    return list(questions)
