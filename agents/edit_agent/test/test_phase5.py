"""
agents/edit_agent/test/test_phase5.py
--------------------------------------
Unit tests for Phase 5 — Intent Classification + State Manager.
Covers the 10 edit query types required by the project spec.

Run:
    MEMORY_BACKEND=mock pytest agents/edit_agent/test/ -v
"""
import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ.setdefault("MEMORY_BACKEND", "mock")

import pytest


# ── IntentClassifier tests (10 query types) ───────────────────────────────────

class TestIntentClassifier:
    def setup_method(self):
        # Force keyword fallback (no Groq key in tests)
        orig = os.environ.pop("GROQ_API_KEY", None)
        self._orig_key = orig
        from agents.edit_agent.intent_classifier import IntentClassifier
        self.clf = IntentClassifier(groq_client=None)

    def teardown_method(self):
        if self._orig_key:
            os.environ["GROQ_API_KEY"] = self._orig_key

    def test_change_voice_tone(self):
        r = self.clf.classify("Change voice tone for narrator")
        assert r["target"] == "audio"
        assert "voice" in r["intent"] or "tone" in r["intent"]

    def test_make_scene_darker(self):
        r = self.clf.classify("Make the scene darker")
        assert r["target"] == "video_frame"
        assert "dark" in r["intent"]

    def test_add_background_music(self):
        r = self.clf.classify("Add background music")
        assert r["target"] == "audio"
        assert "music" in r["intent"] or "background" in r["intent"]

    def test_change_bgm(self):
        r = self.clf.classify("Change BGM to jazz music")
        assert r["target"] == "audio"
        assert r["intent"] == "change_bgm"
        assert r["parameters"]["mood_query"] == "jazz music"

    def test_increase_bgm_volume(self):
        r = self.clf.classify("Increase volume of BGM")
        assert r["target"] == "audio"
        assert r["intent"] == "increase_bgm_volume"
        assert r["parameters"]["volume_factor"] == 1.5

    def test_decrease_bgm_volume(self):
        r = self.clf.classify("Make BGM quieter")
        assert r["target"] == "audio"
        assert r["intent"] == "decrease_bgm_volume"
        assert r["parameters"]["volume_factor"] == 0.5

    def test_remove_subtitle(self):
        r = self.clf.classify("Remove the subtitle")
        assert r["target"] == "video"
        assert "subtitle" in r["intent"]

    def test_change_character_design(self):
        r = self.clf.classify("Change character design for Alex")
        assert r["target"] == "video_frame"
        assert "character" in r["intent"] or "design" in r["intent"]

    def test_speed_up_scene(self):
        r = self.clf.classify("Speed up this scene")
        assert r["target"] == "video"
        assert "speed" in r["intent"]

    def test_regenerate_script(self):
        r = self.clf.classify("Regenerate the script")
        assert r["target"] == "script"
        assert "script" in r["intent"] or "regenerate" in r["intent"]

    def test_make_scene_brighter(self):
        r = self.clf.classify("Make the scene brighter and more vivid")
        assert r["target"] == "video_frame"

    def test_add_subtitle(self):
        r = self.clf.classify("Add subtitle overlay")
        assert r["target"] == "video"

    def test_scene_scoping(self):
        r = self.clf.classify("Make scene 2 darker")
        assert r["scope"] == "scene:2"

    def test_unknown_defaults_to_script(self):
        r = self.clf.classify("zzz gibberish xyzzy")
        assert r["intent"] == "unknown"
        assert r["target"] == "script"

    def test_result_always_has_required_keys(self):
        for query in [
            "change voice", "make darker", "add music",
            "remove subtitle", "regenerate script",
        ]:
            r = self.clf.classify(query)
            for key in ("intent", "target", "scope", "parameters"):
                assert key in r, f"Missing key '{key}' for query: {query}"


# ── EditPlanner tests ─────────────────────────────────────────────────────────

class TestEditPlanner:
    def setup_method(self):
        from agents.edit_agent.planner import EditPlanner
        self.planner = EditPlanner()

    def _intent(self, target, intent_name, scope="all_scenes", params=None):
        return {"intent": intent_name, "target": target, "scope": scope, "parameters": params or {}}

    def test_script_plan_has_three_steps(self):
        plan = self.planner.plan(self._intent("script", "regenerate_script"))
        assert len(plan["steps"]) == 3
        phases = [s["phase"] for s in plan["steps"]]
        assert phases == [1, 2, 3]

    def test_audio_plan_reruns_audio_and_video(self):
        plan = self.planner.plan(self._intent("audio", "change_voice_tone"))
        phases = [s["phase"] for s in plan["steps"]]
        assert 2 in phases
        assert 3 in phases

    def test_video_frame_plan_reruns_images(self):
        plan = self.planner.plan(self._intent("video_frame", "make_scene_darker"))
        assert plan["steps"][0]["action"] == "rerun_images"
        assert plan["steps"][0]["phase"] == 3

    def test_video_plan_uses_compose(self):
        plan = self.planner.plan(self._intent("video", "remove_subtitle"))
        assert plan["steps"][0]["action"] == "rerun_video_compose"
        assert plan["steps"][0]["params"]["use_subtitles"] is False

    def test_add_subtitle_sets_flag(self):
        plan = self.planner.plan(self._intent("video", "add_subtitle"))
        assert plan["steps"][0]["params"]["use_subtitles"] is True

    def test_all_plans_require_snapshot(self):
        for target in ("script", "audio", "video_frame", "video"):
            plan = self.planner.plan(self._intent(target, "test"))
            assert plan["requires_snapshot_before"] is True

    def test_scene_filter_passed_to_images(self):
        plan = self.planner.plan(self._intent("video_frame", "make_scene_darker", scope="scene:3"))
        assert plan["steps"][0]["params"]["scene_filter"] == "3"


# ── StateManager / Storage tests ─────────────────────────────────────────────

class TestStateManager:
    def setup_method(self):
        # Use a temp directory so tests don't pollute data/state_versions
        self._tmpdir = tempfile.mkdtemp()
        import state_manager.storage as _stor
        self._orig_dir  = _stor.STATE_VERSIONS_DIR
        self._orig_idx  = _stor.INDEX_FILE
        _stor.STATE_VERSIONS_DIR = Path(self._tmpdir)
        _stor.INDEX_FILE         = Path(self._tmpdir) / "index.json"

    def teardown_method(self):
        import state_manager.storage as _stor
        _stor.STATE_VERSIONS_DIR = self._orig_dir
        _stor.INDEX_FILE         = self._orig_idx
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _sm(self):
        from state_manager.state_manager import StateManager
        return StateManager()

    def test_snapshot_increments_version(self):
        import state_manager.storage as stor
        stor.write_version(1, {"x":1}, [], "first")
        stor.write_version(2, {"x":2}, [], "second")
        assert stor.latest_version_number() == 2

    def test_read_version_returns_correct_data(self):
        import state_manager.storage as stor
        stor.write_version(1, {"hello": "world"}, ["a.json"], "test")
        snap = stor.read_version(1)
        assert snap["state"]["hello"] == "world"
        assert snap["version"] == 1

    def test_list_versions_newest_first(self):
        import state_manager.storage as stor
        stor.write_version(1, {}, [], "v1")
        stor.write_version(2, {}, [], "v2")
        stor.write_version(3, {}, [], "v3")
        versions = stor.list_versions()
        assert versions[0]["version"] == 3

    def test_delete_version(self):
        import state_manager.storage as stor
        stor.write_version(1, {}, [], "del me")
        assert stor.delete_version(1) is True
        assert stor.read_version(1) is None

    def test_history_returns_list(self):
        from state_manager.history import list_history
        import state_manager.storage as stor
        stor.write_version(1, {}, [], "h1")
        h = list_history()
        assert isinstance(h, list)
        assert h[0]["version"] == 1

    def test_diff_versions(self):
        from state_manager.history import diff_versions
        import state_manager.storage as stor
        stor.write_version(1, {"a": 1}, ["f1.json"], "v1")
        stor.write_version(2, {"a": 2, "b": 3}, ["f1.json","f2.json"], "v2")
        diff = diff_versions(1, 2)
        assert "b" in diff["state_keys_added"]
        assert diff["assets_added"] == 1
