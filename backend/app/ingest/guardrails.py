"""Upload-time guardrail: flag text that looks like instructions aimed at an AI.

This does NOT block or strip anything. The real defence is in the prompts (documents are wrapped in
delimiters and declared data-not-instructions). Flagging makes the attempt visible to the user and in
logs, and gives the eval something to assert on.
"""

import re

PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your)\b"
               r"[^.\n]{0,20}\b(instructions?|prompts?|rules?|guidelines?)\b", re.IGNORECASE),
    re.compile(r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|llm|language model|chatgpt|claude|gpt|"
               r"assistant|screening tools?|automated screen\w*)\b", re.IGNORECASE),
    re.compile(r"\byou are now\b", re.IGNORECASE),
    re.compile(r"\b(system prompt|developer message|jailbreak)\b", re.IGNORECASE),
    re.compile(r"\b(respond|reply|answer|output)\s+only\s+with\b", re.IGNORECASE),
]
MAX_SIGNALS = 3
CONTEXT_CHARS = 60


def injection_signals(text: str) -> list[str]:
    """Return up to 3 short snippets around suspicious phrases (empty list = nothing found)."""
    hits: list[tuple[int, str]] = []
    for pattern in PATTERNS:
        for m in pattern.finditer(text):
            start = max(0, m.start() - 10)
            snippet = " ".join(text[start : m.end() + CONTEXT_CHARS].split())
            hits.append((m.start(), snippet))
    hits.sort()
    seen: list[str] = []
    for _, snippet in hits:
        if not any(snippet in s or s in snippet for s in seen):
            seen.append(snippet)
    return seen[:MAX_SIGNALS]
