"""
Voice Mapping System for Edge-TTS Integration.
Maps character names/personalities to specific Edge-TTS neural voices for variety.
"""

from typing import Dict, Optional, List
from enum import Enum


class EdgeTTSVoice(Enum):
    """Available Edge-TTS neural voices for variety."""
    # Male voices
    JACK_US = "en-US-GuyNeural"
    JAMES_US = "en-US-DavidNeural"
    THOMAS_GB = "en-GB-ThomasNeural"
    OLIVER_GB = "en-GB-OliverNeural"
    RYAN_AU = "en-AU-WilliamNeural"
    RYAN_CA = "en-CA-LiamNeural"
    
    # Female voices
    RACHEL_US = "en-US-AriaNeural"
    JESSICA_US = "en-US-JennyNeural"
    SOPHIA_GB = "en-GB-SoniaNeural"
    EMILY_GB = "en-GB-MiaNeural"
    SARAH_AU = "en-AU-NatashaNeural"
    EMMA_CA = "en-CA-ClaraNeural"
    
    # Additional neutral/character voices
    NARRATOR = "en-US-ArthurNeural"
    REPORTER = "en-GB-RyanNeural"


class VoiceMapper:
    """Maps character names/personalities to Edge-TTS voices."""
    
    # Available voices in preference order (highest to lowest)
    # Reverse this for Jack to get least priority
    MALE_VOICES_PREFERRED = [
        EdgeTTSVoice.RYAN_AU.value,          # Most preferred
        EdgeTTSVoice.OLIVER_GB.value,
        EdgeTTSVoice.THOMAS_GB.value,
        EdgeTTSVoice.JAMES_US.value,
        EdgeTTSVoice.JACK_US.value,          # Least preferred (Jack gets lowest priority)
    ]
    
    FEMALE_VOICES_PREFERRED = [
        EdgeTTSVoice.SARAH_AU.value,         # Most preferred
        EdgeTTSVoice.EMILY_GB.value,
        EdgeTTSVoice.SOPHIA_GB.value,
        EdgeTTSVoice.JESSICA_US.value,
        EdgeTTSVoice.RACHEL_US.value,        # Least preferred
    ]
    
    # Default mappings - can be overridden
    DEFAULT_CHARACTER_VOICES: Dict[str, str] = {
        # Common male names/roles
        "JACK": EdgeTTSVoice.JACK_US.value,
        "JAMES": EdgeTTSVoice.JAMES_US.value,
        "THOMAS": EdgeTTSVoice.THOMAS_GB.value,
        "VLADIMIR": EdgeTTSVoice.OLIVER_GB.value,  # Russian character - British accent adds authority
        "OLIVER": EdgeTTSVoice.OLIVER_GB.value,
        "RYAN": EdgeTTSVoice.RYAN_AU.value,
        "LIAM": EdgeTTSVoice.RYAN_CA.value,
        "NARRATOR": EdgeTTSVoice.NARRATOR.value,
        "HERO": EdgeTTSVoice.JACK_US.value,
        
        # Common female names/roles
        "RACHEL": EdgeTTSVoice.RACHEL_US.value,
        "JESSICA": EdgeTTSVoice.JESSICA_US.value,
        "SOPHIA": EdgeTTSVoice.SOPHIA_GB.value,
        "EMILY": EdgeTTSVoice.EMILY_GB.value,
        "SARAH": EdgeTTSVoice.SARAH_AU.value,
        "EMMA": EdgeTTSVoice.EMMA_CA.value,
        "ALEXANDRA": EdgeTTSVoice.SOPHIA_GB.value,  # Russian female - British accent
        "NATASHA": EdgeTTSVoice.EMILY_GB.value,
    }
    
    def __init__(self, custom_mappings: Optional[Dict[str, str]] = None, reverse_preference: bool = True):
        """
        Initialize the voice mapper.
        
        Args:
            custom_mappings: Optional custom character-to-voice mappings to override defaults
            reverse_preference: If True (default), Jack gets least priority voice; if False, normal preference order
        """
        self.character_voices = self.DEFAULT_CHARACTER_VOICES.copy()
        if custom_mappings:
            self.character_voices.update(custom_mappings)
        self.voice_assignment_history: Dict[str, str] = {}
        self.reverse_preference = reverse_preference
        self.assignment_counter = 0  # Track how many characters we've assigned voices to
    
    def get_voice_for_character(self, character_name: str) -> str:
        """
        Get the Edge-TTS voice for a character.
        Uses character's name or personality to map to a voice.
        
        Args:
            character_name: Name of the character
            
        Returns:
            Edge-TTS voice string (e.g., "en-US-GuyNeural")
        """
        # Normalize character name
        normalized_name = character_name.upper().strip()
        
        # Check if we have a direct mapping
        if normalized_name in self.character_voices:
            voice = self.character_voices[normalized_name]
            self.voice_assignment_history[normalized_name] = voice
            return voice
        
        # If not found, assign a voice based on gender detection or default
        voice = self._assign_voice_by_name(normalized_name)
        self.character_voices[normalized_name] = voice
        self.voice_assignment_history[normalized_name] = voice
        self.assignment_counter += 1  # Track assignments for rotation
        return voice
    
    def _assign_voice_by_name(self, character_name: str) -> str:
        """
        Assign a voice based on character name analysis.
        Uses simple gender inference from name to select appropriate voice.
        With reverse_preference=True, Jack gets the least preferred voice.
        
        Args:
            character_name: Name of the character
            
        Returns:
            Edge-TTS voice string
        """
        # Simple gender detection based on common name endings
        female_endings = ('A', 'E', 'I', 'H', 'NA', 'IA', 'AH', 'Y')
        
        if character_name.endswith(female_endings):
            # Use female voice - rotate through available options
            # With reverse_preference=True, use voices in reverse order (highest to lowest priority)
            available_female = self.FEMALE_VOICES_PREFERRED if self.reverse_preference else list(reversed(self.FEMALE_VOICES_PREFERRED))
            voice_index = self.assignment_counter % len(available_female)
            return available_female[voice_index]
        else:
            # Use male voice - rotate through available options
            # With reverse_preference=True, use voices in reverse order (highest to lowest priority)
            available_male = self.MALE_VOICES_PREFERRED if self.reverse_preference else list(reversed(self.MALE_VOICES_PREFERRED))
            voice_index = self.assignment_counter % len(available_male)
            return available_male[voice_index]
    
    def get_all_character_voices(self) -> Dict[str, str]:
        """Get all character-to-voice mappings."""
        return self.character_voices.copy()
    
    def set_character_voice(self, character_name: str, voice: str) -> None:
        """
        Manually set a specific voice for a character.
        
        Args:
            character_name: Name of the character
            voice: Edge-TTS voice string
        """
        self.character_voices[character_name.upper().strip()] = voice
    
    @staticmethod
    def get_available_voices() -> List[str]:
        """Get list of all available Edge-TTS voices."""
        return [voice.value for voice in EdgeTTSVoice]
