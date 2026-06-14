"""
mcp/tools/audio_tools/voice_mapper.py
---------------------------------------
Maps character names to Edge-TTS neural voices.
"""
from typing import Dict, List, Optional
from enum import Enum


class EdgeTTSVoice(Enum):
    JACK_US    = "en-US-GuyNeural"
    JAMES_US   = "en-US-DavidNeural"
    THOMAS_GB  = "en-GB-ThomasNeural"
    OLIVER_GB  = "en-GB-OliverNeural"
    RYAN_AU    = "en-AU-WilliamNeural"
    RYAN_CA    = "en-CA-LiamNeural"
    RACHEL_US  = "en-US-AriaNeural"
    JESSICA_US = "en-US-JennyNeural"
    SOPHIA_GB  = "en-GB-SoniaNeural"
    EMILY_GB   = "en-GB-MiaNeural"
    SARAH_AU   = "en-AU-NatashaNeural"
    EMMA_CA    = "en-CA-ClaraNeural"
    NARRATOR   = "en-US-ArthurNeural"
    REPORTER   = "en-GB-RyanNeural"


class VoiceMapper:
    MALE_VOICES_PREFERRED = [
        EdgeTTSVoice.RYAN_AU.value,
        EdgeTTSVoice.OLIVER_GB.value,
        EdgeTTSVoice.THOMAS_GB.value,
        EdgeTTSVoice.JAMES_US.value,
        EdgeTTSVoice.JACK_US.value,
    ]
    FEMALE_VOICES_PREFERRED = [
        EdgeTTSVoice.SARAH_AU.value,
        EdgeTTSVoice.EMILY_GB.value,
        EdgeTTSVoice.SOPHIA_GB.value,
        EdgeTTSVoice.JESSICA_US.value,
        EdgeTTSVoice.RACHEL_US.value,
    ]
    DEFAULT_CHARACTER_VOICES: Dict[str, str] = {
        "JACK": EdgeTTSVoice.JACK_US.value,
        "JAMES": EdgeTTSVoice.JAMES_US.value,
        "THOMAS": EdgeTTSVoice.THOMAS_GB.value,
        "VLADIMIR": EdgeTTSVoice.OLIVER_GB.value,
        "OLIVER": EdgeTTSVoice.OLIVER_GB.value,
        "RYAN": EdgeTTSVoice.RYAN_AU.value,
        "LIAM": EdgeTTSVoice.RYAN_CA.value,
        "NARRATOR": EdgeTTSVoice.NARRATOR.value,
        "HERO": EdgeTTSVoice.JACK_US.value,
        "ALEX": EdgeTTSVoice.JAMES_US.value,
        "MORGAN": EdgeTTSVoice.THOMAS_GB.value,
        "RACHEL": EdgeTTSVoice.RACHEL_US.value,
        "JESSICA": EdgeTTSVoice.JESSICA_US.value,
        "SOPHIA": EdgeTTSVoice.SOPHIA_GB.value,
        "EMILY": EdgeTTSVoice.EMILY_GB.value,
        "SARAH": EdgeTTSVoice.SARAH_AU.value,
        "EMMA": EdgeTTSVoice.EMMA_CA.value,
        "ALEXANDRA": EdgeTTSVoice.SOPHIA_GB.value,
        "NATASHA": EdgeTTSVoice.EMILY_GB.value,
    }

    def __init__(
        self,
        custom_mappings: Optional[Dict[str, str]] = None,
        reverse_preference: bool = True,
    ):
        self.character_voices = self.DEFAULT_CHARACTER_VOICES.copy()
        if custom_mappings:
            self.character_voices.update(custom_mappings)
        self.reverse_preference = reverse_preference
        self.assignment_counter = 0

    def get_voice_for_character(self, character_name: str) -> str:
        key = character_name.upper().strip()
        if key in self.character_voices:
            return self.character_voices[key]
        voice = self._assign_voice_by_name(key)
        self.character_voices[key] = voice
        self.assignment_counter += 1
        return voice

    def _assign_voice_by_name(self, name: str) -> str:
        female_endings = ("A", "E", "I", "H", "NA", "IA", "AH", "Y")
        pool = (
            self.FEMALE_VOICES_PREFERRED
            if name.endswith(female_endings)
            else self.MALE_VOICES_PREFERRED
        )
        return pool[self.assignment_counter % len(pool)]

    def get_all_character_voices(self) -> Dict[str, str]:
        return self.character_voices.copy()

    def set_character_voice(self, character_name: str, voice: str) -> None:
        self.character_voices[character_name.upper().strip()] = voice

    @staticmethod
    def get_available_voices() -> List[str]:
        return [v.value for v in EdgeTTSVoice]
