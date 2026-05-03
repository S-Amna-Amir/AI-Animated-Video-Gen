"""Workflow builder — retained for compatibility."""

BASE_WORKFLOW = {
    "3": {"inputs": {"seed": 0, "steps": 20, "cfg": 7}},
    "6": {"inputs": {"text": ""}},
    "7": {"inputs": {"text": ""}},
    "9": {"inputs": {"filename_prefix": ""}}
}

def build_workflow(positive_prompt: str, negative_prompt: str, 
                   scene_id: str, seed: int = None) -> dict:
    """Stub retained for backward compatibility with tests."""
    import copy
    workflow = copy.deepcopy(BASE_WORKFLOW)
    workflow["6"]["inputs"]["text"] = positive_prompt
    workflow["7"]["inputs"]["text"] = negative_prompt
    workflow["9"]["inputs"]["filename_prefix"] = f"scene_{scene_id}"
    return workflow
