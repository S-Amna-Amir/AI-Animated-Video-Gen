"""
Phase 2 Audio Generation Test Script.
Tests the audio agent with dummy Phase 1 data from data/outputs/Phase1.
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# Add parent directory to path for imports and change working directory
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from agents.audio_agent.agent import AudioAgent, run_audio_agent


async def test_phase2_with_dummy_data():
    """
    Test Phase 2 audio generation with dummy Phase 1 data.
    """
    
    print("\n" + "="*80)
    print("PHASE 2 - AUDIO GENERATION TEST")
    print("="*80 + "\n")
    
    # Configuration
    phase1_data_dir = "data/outputs/Phase1"
    phase2_output_dir = "data/outputs/Phase2"
    
    print(f"📁 Phase 1 Data Dir: {phase1_data_dir}")
    print(f"📁 Phase 2 Output Dir: {phase2_output_dir}\n")
    
    # Verify Phase 1 data exists
    phase1_path = Path(phase1_data_dir)
    if not phase1_path.exists():
        print(f"❌ Phase 1 data directory not found: {phase1_data_dir}")
        return
    
    # Check for required files
    scene_files = [
        phase1_path / "scene_manifest_auto.json",
        phase1_path / "scene_manifest_manual.json",
        phase1_path / "scene_manifest.json"
    ]
    
    scene_file = None
    for f in scene_files:
        if f.exists():
            scene_file = f
            break
    
    if not scene_file:
        print(f"❌ No scene manifest found in {phase1_data_dir}")
        return
    
    print(f"✅ Found scene manifest: {scene_file.name}")
    
    # Check character database
    char_files = [
        phase1_path / "character_db_auto.json",
        phase1_path / "character_db_manual.json",
        phase1_path / "character_db.json"
    ]
    
    char_file = None
    for f in char_files:
        if f.exists():
            char_file = f
            break
    
    if not char_file:
        print(f"❌ No character database found in {phase1_data_dir}")
        return
    
    print(f"✅ Found character database: {char_file.name}\n")
    
    # Load and display Phase 1 data summary
    with open(scene_file) as f:
        scene_manifest = json.load(f)
    
    with open(char_file) as f:
        character_db = json.load(f)
    
    scenes = scene_manifest.get("scenes", [])
    characters = character_db.get("characters", []) if isinstance(character_db, dict) else character_db
    
    total_dialogues = sum(len(scene.get("dialogue", [])) for scene in scenes)
    
    print("📋 Phase 1 Data Summary:")
    print(f"  • Total Scenes: {len(scenes)}")
    print(f"  • Total Characters: {len(characters)}")
    print(f"  • Total Dialogue Lines: {total_dialogues}\n")
    
    print("🎭 Characters:")
    for char in characters[:5]:  # Show first 5 characters
        char_name = char.get("name", "UNKNOWN")
        char_role = char.get("role", "unknown")
        print(f"  • {char_name} ({char_role})")
    if len(characters) > 5:
        print(f"  ... and {len(characters) - 5} more\n")
    
    # Run Phase 2
    print("\n" + "-"*80)
    print("🎬 Starting Phase 2 Audio Generation...")
    print("-"*80 + "\n")
    
    try:
        results = await run_audio_agent(
            phase1_dir=phase1_data_dir,
            phase2_dir=phase2_output_dir,
            run_id=None  # Auto-generate run ID
        )
        
        # Display results
        print("\n" + "="*80)
        print("📊 PHASE 2 RESULTS")
        print("="*80 + "\n")
        
        if results.get("status") == "success":
            print("✅ Phase 2 Processing: SUCCESS\n")
            
            print(f"Run ID: {results.get('run_id')}")
            print(f"Total Scenes: {results.get('total_scenes')}")
            print(f"Total Dialogues: {results.get('total_dialogues')}")
            print(f"Audio Files Generated: {results.get('audio_files_generated')}")
            print(f"Total Duration: {results.get('total_duration_ms')}ms "
                  f"({results.get('total_duration_ms') / 1000:.1f}s)\n")
            
            print(f"Output Directory: {results.get('output_directory')}")
            print(f"Timing Manifest: {results.get('timing_manifest_path')}\n")
            
            # Display character-to-voice mappings
            voices = results.get('character_voices_used', {})
            print(f"Character Voice Mappings ({len(voices)} characters):")
            for char_name, voice in sorted(voices.items()):
                print(f"  • {char_name:15} → {voice}")
            
            # Display workflow progress
            progress = results.get('workflow_progress', {})
            print(f"\n📈 Workflow Progress:")
            print(f"  Completed Steps: {progress.get('completed_steps')}/{progress.get('total_steps')}")
            for step in progress.get('completed', []):
                print(f"    ✓ {step}")
            
            print("\n" + "="*80)
            print("✨ Phase 2 Audio Generation Complete!")
            print("="*80 + "\n")
            
            return results
        
        else:
            print("❌ Phase 2 Processing: FAILED\n")
            print(f"Error: {results.get('error')}\n")
            
            progress = results.get('workflow_progress', {})
            print(f"Workflow Progress:")
            print(f"  Completed Steps: {progress.get('completed_steps')}/{progress.get('total_steps')}")
            print(f"  Failed Steps: {progress.get('failed_steps')}\n")
            
            return None
    
    except Exception as e:
        print(f"❌ Error during Phase 2 execution: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main entry point."""
    results = asyncio.run(test_phase2_with_dummy_data())
    
    if results and results.get("status") == "success":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
