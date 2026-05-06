import os
import json
import logging
from typing import Any, Dict
from pydantic import BaseModel, Field
import groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EditIntent(BaseModel):
    intent: str = Field(description="Short snake_case label representing the core action, e.g., 'change_voice_tone', 'undo', 'adjust_visual_style'.")
    target: str = Field(description="The component being targeted. Must be one of: 'audio', 'video_frame', 'video', 'script', 'system'.")
    scope: str = Field(description="What exactly is being targeted, e.g., 'character:Narrator', 'scene:2', 'full', 'system'.")
    parameters: Dict[str, Any] = Field(description="Any relevant settings for the edit, e.g., {'tone': 'whispered'}, {'aesthetic': 'darker'}, etc.")

class IntentClassifier:
    def __init__(self, groq_client=None):
        self.groq_api_key = os.getenv("GROQ_API_KEY") or os.getenv("Groq-api")
        if groq_client:
            self.client = groq_client
        elif self.groq_api_key:
            self.client = groq.Groq(api_key=self.groq_api_key)
        else:
            logger.warning("GROQ_API_KEY or Groq-api not found. Intent classifier will not work.")
            self.client = None

    def classify(self, query: str) -> dict[str, Any]:
        if not self.client:
            return self._fallback_classify(query)

        prompt = f"""You are an intent classifier for an AI-animated video generation system.
Your job is to analyze a plain English edit command from a user and extract the structured intent.

Output exactly a JSON object matching this schema:
{{
  "intent": "short_snake_case_label",
  "target": "one of: audio, video_frame, video, script, system",
  "scope": "what is being targeted, e.g. character:Narrator, scene:2, full, system",
  "parameters": {{
    "key1": "value1",
    "key2": "value2"
  }}
}}

Examples of mapping:
1. "Make the narrator sound more dramatic" ->
{{"intent": "change_voice_tone", "target": "audio", "scope": "character:Narrator", "parameters": {{"tone": "dramatic"}}}}

2. "The second scene looks too bright" ->
{{"intent": "adjust_visual_style", "target": "video_frame", "scope": "scene:2", "parameters": {{"aesthetic": "darker"}}}}

3. "Undo the last change" ->
{{"intent": "undo", "target": "system", "scope": "system", "parameters": {{}}}}

4. "Remove subtitles from the final video" ->
{{"intent": "remove_subtitles", "target": "video", "scope": "full", "parameters": {{}}}}

5. "Speed up scene 3" ->
{{"intent": "adjust_timing", "target": "video", "scope": "scene:3", "parameters": {{"speed_factor": 1.5}}}}

Now classify the following query:
Query: "{query}"

Output ONLY valid JSON.
"""
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that responds ONLY with valid JSON matching the requested schema. No markdown wrapping. Output exactly a valid JSON object."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            # If the response is wrapped in code blocks, strip them
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            parsed = json.loads(content.strip())
            
            # validate with Pydantic
            intent_obj = EditIntent(**parsed)
            return intent_obj.model_dump()
            
        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            return self._fallback_classify(query)

    def _fallback_classify(self, query: str) -> dict[str, Any]:
        return {
            "intent": "custom_edit",
            "target": "video",
            "scope": "full",
            "parameters": {"query": query},
        }

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    queries = [
        "Make the narrator sound more dramatic",
        "The second scene looks too bright",
        "Add some sad background music",
        "Rewrite the story with a happier ending",
        "Remove subtitles from the final video",
        "Speed up scene 3",
        "Change the villain's voice to sound robotic",
        "Make all scenes look more cinematic",
        "The dialogue in scene 1 feels too long, shorten it",
        "Undo the last change"
    ]
    
    classifier = IntentClassifier()
    for q in queries:
        res = classifier.classify(q)
        print(f"Query: {q}")
        print(f"Output: {json.dumps(res, indent=2)}\n")
