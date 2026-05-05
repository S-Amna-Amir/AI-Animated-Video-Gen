"""
LLM Text Generator Tool
MCP tool that wraps the Groq API for free-form text generation.
Used by the Story Agent for narrative and character generation.
"""

import os
from typing import Optional
from groq import Groq

from mcp.base_tool import BaseTool


class TextGeneratorTool(BaseTool):
    name = "text_generator"
    description = "Generates free-form text using Groq (llama-3.3-70b-versatile)."

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Add it to your .env file."
            )
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def run(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.8,
    ) -> str:
        """
        Call the Groq Chat Completions API and return the assistant text.

        Args:
            prompt:      User-turn message.
            system:      Optional system prompt.
            max_tokens:  Max output tokens (default 4096).
            temperature: Sampling temperature (default 0.8).

        Returns:
            The raw text content of the model response.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
