# polaris_iq/planning/plan_generator.py

import ast
import json
import logging
import re
from polaris_iq.planning.plan_schema import QueryPlan

logger = logging.getLogger("polaris_iq.plan_generator")


def _extract_json(text: str) -> str:
    """Extract JSON from LLM output, handling markdown fences and stray text."""

    text = text.strip()

    # 1. Try to extract content from markdown code fences
    fence_match = re.search(r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # 2. Fall back: extract the outermost { ... } block
    start = text.find("{")
    if start != -1:
        # Find the matching closing brace by counting depth
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        # If we ran out of text (truncated output), try to fix it
        # Add missing closing braces
        truncated = text[start:]
        truncated += "}" * depth
        return truncated

    # 3. Nothing found — return as-is and let json.loads raise a clear error
    return text


def _sanitize_json(text: str) -> str:
    """Fix common LLM JSON quirks so standard json.loads succeeds."""

    # Replace Python booleans/None with JSON equivalents
    text = re.sub(r'\bTrue\b', 'true', text)
    text = re.sub(r'\bFalse\b', 'false', text)
    text = re.sub(r'\bNone\b', 'null', text)

    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Replace single quotes with double quotes (handles nested strings carefully)
    # Only do this if there are no double-quoted strings already
    if '"' not in text:
        text = text.replace("'", '"')
    else:
        # Mixed quotes: try to fix single-quoted keys/values
        # Replace single-quoted keys: 'key': -> "key":
        text = re.sub(r"(?<=[{,\s])\s*'([^']+?)'\s*:", r' "\1":', text)
        # Replace single-quoted string values: : 'value' -> : "value"
        text = re.sub(r":\s*'([^']*?)'\s*(?=[,}\]])", r': "\1"', text)

    return text


def _parse_json_flexible(text: str) -> dict:
    """Parse JSON string, with sanitization and ast.literal_eval fallback."""
    # First attempt: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Second attempt: sanitize common LLM quirks and retry
    try:
        sanitized = _sanitize_json(text)
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass

    # Third attempt: ast.literal_eval for Python-dict-style output
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    raise json.JSONDecodeError(
        f"Could not parse LLM output as JSON after sanitization",
        text,
        0,
    )


def _build_prompt(user_query: str, context: str) -> str:
    """Build a concise prompt optimized for smaller LLMs."""

    return f"""You are a JSON generator. Output ONLY a JSON object, nothing else.

Pick the correct intent for the user's question and fill in the JSON.

Intents: aggregation, correlation_analysis, regression_analysis, visualization

Rules:
- For aggregation: set statistics.parameters with "columns", "group_by", "aggregate" (AVG/SUM/COUNT/MIN/MAX)
- For visualization: set execution_engine to "visualization", statistics.parameters with "x", "y", "chart_type" (scatter/line/bar/histogram/pie)
- For correlation: set statistics.parameters with "columns" (list of 2 column names)
- For regression: set prediction with "type": "linear_regression", parameters with "independent" and "dependent"

{context}

User question: {user_query}

Respond with ONLY this JSON structure (fill in the values):
{{"intent":"<intent>","data_scope":{{"tables":["<table_name>"]}},"statistics":{{"type":["<stat_type>"],"parameters":{{<params>}}}},"execution_engine":"<engine>","explanation_level":"brief"}}"""


def generate_structured_plan(user_query: str, context: str, model) -> QueryPlan:

    prompt = _build_prompt(user_query, context)

    max_retries = 2
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # On retry, add a stronger nudge
                retry_prompt = prompt + "\n\nIMPORTANT: Output ONLY valid JSON. No text before or after the JSON object."
                raw_output = model.generate(retry_prompt, temperature=0.1, max_tokens=600)
            else:
                raw_output = model.generate(prompt, temperature=0.0, max_tokens=600)

            logger.info(f"[Attempt {attempt+1}] LLM raw output: {raw_output[:500]}")

            if not raw_output or not raw_output.strip():
                last_error = ValueError("LLM returned empty output")
                logger.warning(f"[Attempt {attempt+1}] LLM returned empty output, retrying...")
                continue

            cleaned = _extract_json(raw_output)
            logger.info(f"[Attempt {attempt+1}] Extracted JSON: {cleaned[:500]}")

            parsed = _parse_json_flexible(cleaned)
            return QueryPlan(**parsed)

        except Exception as e:
            last_error = e
            logger.warning(f"[Attempt {attempt+1}] Failed to parse plan: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying... ({attempt+2}/{max_retries+1})")

    # All retries exhausted
    raise last_error
