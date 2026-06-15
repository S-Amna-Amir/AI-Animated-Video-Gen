"""
mcp/tools/audio_tools/voice_mapper.py
---------------------------------------
Maps character names to Edge-TTS neural voices.
"""
from typing import Dict, List, Optional
from enum import Enum


class EdgeTTSVoice(Enum):
    JACK_US    = "en-US-GuyNeural"
    JAMES_US   = "en-GB-RyanNeural"       # DavidNeural broken — replaced
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
    NARRATOR   = "en-GB-RyanNeural"       # ArthurNeural broken — replaced
    REPORTER   = "en-GB-ThomasNeural"


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
        "JACK":      EdgeTTSVoice.JACK_US.value,
        "JAMES":     EdgeTTSVoice.JAMES_US.value,
        "THOMAS":    EdgeTTSVoice.THOMAS_GB.value,
        "VLADIMIR":  EdgeTTSVoice.OLIVER_GB.value,
        "OLIVER":    EdgeTTSVoice.OLIVER_GB.value,
        "RYAN":      EdgeTTSVoice.RYAN_AU.value,
        "LIAM":      EdgeTTSVoice.RYAN_CA.value,
        "NARRATOR":  EdgeTTSVoice.NARRATOR.value,
        "HERO":      EdgeTTSVoice.JACK_US.value,
        "ALEX":      EdgeTTSVoice.JACK_US.value,       # was DavidNeural (broken)
        "MORGAN":    EdgeTTSVoice.THOMAS_GB.value,
        "RACHEL":    EdgeTTSVoice.RACHEL_US.value,
        "JESSICA":   EdgeTTSVoice.JESSICA_US.value,
        "SOPHIA":    EdgeTTSVoice.SOPHIA_GB.value,
        "EMILY":     EdgeTTSVoice.EMILY_GB.value,
        "SARAH":     EdgeTTSVoice.SARAH_AU.value,
        "EMMA":      EdgeTTSVoice.EMMA_CA.value,
        "ALEXANDRA": EdgeTTSVoice.SOPHIA_GB.value,
        "NATASHA":   EdgeTTSVoice.EMILY_GB.value,
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
        """
        Heuristic voice assignment for unknown character names.
        Checks keyword indicators first, then falls back to vowel ending.
        """
        lower = name.lower()

        # ── Keyword-based gender detection ────────────────────────────────────
        female_keywords = (
            "woman", "girl", "lady", "female", "mother", "mom", "mum",
            "sister", "wife", "queen", "princess", "aunt", "grandma",
            "grandmother", "ms", "mrs", "miss", "she", "her",
        )
        male_keywords = (
            "man", "boy", "male", "father", "dad", "brother", "husband",
            "king", "prince", "uncle", "grandpa", "grandfather",
            "mr", "sir", "he", "his", "guy", "dude",
        )

        for kw in female_keywords:
            if kw in lower.split() or lower == kw or lower.endswith(" " + kw) or lower.startswith(kw + " "):
                pool = self.FEMALE_VOICES_PREFERRED
                voice = pool[self.assignment_counter % len(pool)]
                return voice

        for kw in male_keywords:
            if kw in lower.split() or lower == kw or lower.endswith(" " + kw) or lower.startswith(kw + " "):
                pool = self.MALE_VOICES_PREFERRED
                voice = pool[self.assignment_counter % len(pool)]
                return voice

        # ── Vowel-ending fallback (weak signal) ───────────────────────────────
        female_endings = ("a", "e", "i", "na", "ia", "ah")
        last_word = lower.split()[-1] if lower.split() else lower
        pool = (
            self.FEMALE_VOICES_PREFERRED
            if any(last_word.endswith(fe) for fe in female_endings)
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
