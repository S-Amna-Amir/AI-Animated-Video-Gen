"""
agents/audio_agent/enhanced_agent.py
--------------------------------------
Re-export shim so test_phase2.py's
  `from agents.audio_agent.enhanced_agent import EnhancedAudioAgent`
keeps working. All logic lives in agent.py.
"""
from agents.audio_agent.agent import EnhancedAudioAgent, AudioAgent, run_audio_agent

__all__ = ["EnhancedAudioAgent", "AudioAgent", "run_audio_agent"]
