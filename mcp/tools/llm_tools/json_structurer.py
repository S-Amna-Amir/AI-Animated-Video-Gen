"""
JSON Structurer Tool
Prompts Groq to produce or repair structured JSON output and validates
it against a Pydantic model. Handles markdown fence stripping and retries.
"""

import json
import re
import os
from typing import Any, Optional, Type
from pydantic import BaseModel, ValidationError
from groq import Groq

from mcp.base_tool import BaseTool


class JsonStructurerTool(BaseTool):
    name = "json_structurer"
    description = (
        "Calls Groq with a schema-aware prompt and returns a validated "
        "Pydantic model instance. Retries on parse/validation errors."
    )

    def __init__(self, max_retries: int = 3):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY not set.")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"
        self.max_retries = max_retries

    # ─── Public API ──────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        schema_class: Type[BaseModel],
        system: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> BaseModel:
        """
        Generate + validate a Pydantic object.

        Args:
            prompt:       Instruction describing what JSON to produce.
            schema_class: Pydantic model to validate against.
            system:       Optional system prompt prefix.
            raw_text:     If provided, structurer attempts to parse this first
                          (skips generation on first try).
        Returns:
            Validated instance of schema_class.
        Raises:
            ValueError after max_retries unsuccessful attempts.
        """
        attempt_text = raw_text
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            # ── Step 1: generate if we don't have text yet ──────────────────
            if attempt_text is None:
                attempt_text = self._generate(prompt, system, schema_class)

            # ── Step 2: strip markdown fences ───────────────────────────────
            clean = self._strip_fences(attempt_text)

            # ── Step 3: parse JSON ───────────────────────────────────────────
            try:
                data = json.loads(clean)
            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                attempt_text = None  # regenerate next round
                continue

            # ── Step 4: validate with Pydantic ───────────────────────────────
            try:
                return schema_class(**data)
            except (ValidationError, TypeError) as e:
                last_error = f"Schema validation error: {e}"
                # Feed error back so model can correct itself
                prompt = self._repair_prompt(prompt, clean, str(e), schema_class)
                attempt_text = None
                continue

        raise ValueError(
            f"JsonStructurerTool failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def parse_only(self, raw_text: str, schema_class: Type[BaseModel]) -> BaseModel:
        """Parse + validate raw text without calling the LLM."""
        clean = self._strip_fences(raw_text)
        data = json.loads(clean)
        return schema_class(**data)

    # ─── Internals ───────────────────────────────────────────────────────────

    def _generate(
        self, prompt: str, system: Optional[str], schema_class: Type[BaseModel]
    ) -> str:
        schema_hint = json.dumps(schema_class.schema(), indent=2)
        full_system = (
            (system or "")
            + "\n\nYou MUST respond with ONLY valid JSON that conforms to this schema "
            "(no markdown, no preamble, no trailing text):\n"
            + schema_hint
        )
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    def _repair_prompt(
        self,
        original_prompt: str,
        bad_json: str,
        error: str,
        schema_class: Type[BaseModel],
    ) -> str:
        return (
            f"{original_prompt}\n\n"
            f"Your previous attempt produced invalid JSON:\n```\n{bad_json[:500]}\n```\n"
            f"Validation error: {error}\n"
            "Please correct the JSON and return ONLY the fixed JSON object."
        )

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove ```json ... ``` or ``` ... ``` wrappers."""
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()
