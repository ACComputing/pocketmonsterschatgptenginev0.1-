"""
chatgptred4k1.0: Professor Battle Prototype
--------------------------------------------
A single-file, no-assets Pygame prototype inspired by classic handheld
monster RPGs. It is intentionally original: placeholder monsters, placeholder
professor, and custom menus instead of copied commercial assets.

Run:
    pip install pygame
    python chatgptred4k1.0.py

Self-test without opening a real window:
    python chatgptred4k1.0.py --self-test

Controls:
    Arrow keys / WASD  Move cursor or player
    Z / Enter / Space Confirm / interact
    X / Backspace     Cancel
    Esc / M           Pause menu in overworld

Notes:
    - 60 FPS fixed loop.
    - Internal 240x160 retro handheld canvas scaled 3x.
    - No external images or sound files are loaded.
    - Procedural chiptune OST: calm field loop plus a fast professor boss theme.
    - Progress saves to a small JSON file beside this script.
    - Procedural SFX use math-generated waveforms, with no imported audio files.
    - Code is written to stay compatible with modern Python, including Python 3.14.
"""

import json
import math
import os
import random
import sys
import warnings
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*", category=UserWarning)
if "--self-test" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

try:
    import pygame
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Pygame is required. Install it with: python -m pip install pygame"
    ) from exc

# -----------------------------------------------------------------------------
# Display / engine constants
# -----------------------------------------------------------------------------

GAME_TITLE = "chatgptred4k1.0"
WINDOW_TITLE = "chatgptred4k1.0 - Professor Battle Prototype"

LOGICAL_W = 240
LOGICAL_H = 160
SCALE = 3
FPS = 60
TILE = 16
PLAYER_SPEED = 1  # 1 px/frame at 60 FPS: classic Gameboy movement speed.
TEXT_REVEAL_SPEED = 1.0  # 1 char/frame for authentic retro text pace.
TEXT_SPEEDS = {"FAST": 1.0, "MID": 0.5}
SAVE_SCHEMA_VERSION = 1
SAVE_FILE_NAME = "chatgptred4k1_0_save.json"
AUDIO_SAMPLE_RATE = 22050
AUDIO_BUFFER_SIZE = 512
PYTHON_TARGET_COMPAT = "3.14"  # Python 3.14-compatible; `import python3.14` is not valid syntax.

# -----------------------------------------------------------------------------
# Palette: original placeholder colors, not imported game assets.
# -----------------------------------------------------------------------------

WHITE = (248, 248, 248)
BLACK = (16, 16, 16)
INK = (36, 36, 44)
SHADOW = (96, 96, 104)
WINDOW = (248, 248, 248)
WINDOW_2 = (226, 232, 246)
FRAME = (80, 88, 128)
FRAME_DARK = (40, 48, 88)
GRASS = (88, 176, 88)
GRASS_DARK = (64, 136, 68)
PATH = (208, 184, 128)
PATH_DARK = (176, 152, 104)
TREE = (32, 112, 64)
TREE_DARK = (24, 80, 48)
WATER = (88, 144, 216)
HEAL_RED = (216, 64, 88)
HEAL_PINK = (248, 144, 160)
PLAYER_BLUE = (48, 96, 208)
PLAYER_HAT = (208, 48, 56)
PROF_COAT = (232, 232, 224)
PROF_GRAY = (112, 112, 120)
ENEMY_GREEN = (112, 184, 120)
ENEMY_DARK = (40, 80, 48)
ALLY_BLUE = (96, 160, 224)
ALLY_DARK = (40, 88, 136)
HP_GREEN = (72, 184, 72)
HP_YELLOW = (232, 184, 48)
HP_RED = (208, 56, 48)

DIRS = {
    "down": (0, 1),
    "up": (0, -1),
    "left": (-1, 0),
    "right": (1, 0),
}

# -----------------------------------------------------------------------------
# Battle data
# -----------------------------------------------------------------------------


@dataclass
class Move:
    name: str
    power: int
    accuracy: float
    max_pp: int
    pp: int = field(init=False)

    def __post_init__(self) -> None:
        self.pp = self.max_pp

    def clone(self) -> "Move":
        return Move(self.name, self.power, self.accuracy, self.max_pp)


@dataclass
class Monster:
    name: str
    level: int
    max_hp: int
    attack: int
    defense: int
    speed: int
    moves: List[Move]
    hp: int = field(init=False)

    def __post_init__(self) -> None:
        self.hp = self.max_hp

    @property
    def fainted(self) -> bool:
        return self.hp <= 0

    def heal_full(self) -> None:
        self.hp = self.max_hp
        for move in self.moves:
            move.pp = move.max_pp

    def clone(self) -> "Monster":
        return Monster(
            self.name,
            self.level,
            self.max_hp,
            self.attack,
            self.defense,
            self.speed,
            [m.clone() for m in self.moves],
        )


# -----------------------------------------------------------------------------
# Drawing helpers
# -----------------------------------------------------------------------------


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def draw_window(surface: pygame.Surface, rect: pygame.Rect) -> None:
    pygame.draw.rect(surface, FRAME_DARK, rect)
    inner = rect.inflate(-2, -2)
    pygame.draw.rect(surface, WINDOW, inner)
    pygame.draw.rect(surface, FRAME, inner, 1)


def draw_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    color: Tuple[int, int, int] = INK,
) -> None:
    surface.blit(font.render(text, False, color), (x, y))


def wrap_text(font: pygame.font.Font, text: str, max_width: int) -> List[str]:
    words = text.split(" ")
    lines: List[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def draw_hp_bar(surface: pygame.Surface, x: int, y: int, width: int, hp: int, max_hp: int) -> None:
    pygame.draw.rect(surface, INK, (x, y, width, 5), 1)
    ratio = 0 if max_hp <= 0 else max(0.0, min(1.0, hp / max_hp))
    fill_width = int((width - 2) * ratio)
    if ratio > 0.50:
        color = HP_GREEN
    elif ratio > 0.20:
        color = HP_YELLOW
    else:
        color = HP_RED
    pygame.draw.rect(surface, color, (x + 1, y + 1, fill_width, 3))


# -----------------------------------------------------------------------------
# Text box
# -----------------------------------------------------------------------------


class TextBox:
    def __init__(self, font: pygame.font.Font) -> None:
        self.font = font
        self.messages: List[str] = []
        self.current = ""
        self.reveal = 0.0
        self.reveal_speed = TEXT_REVEAL_SPEED
        self.active = False

    def start(self, messages: Sequence[str]) -> None:
        self.messages = list(messages)
        self.current = self.messages.pop(0) if self.messages else ""
        self.reveal = 0.0
        self.active = bool(self.current or self.messages)

    def update(self) -> None:
        if self.active:
            self.reveal = min(float(len(self.current)), self.reveal + self.reveal_speed)

    def advance(self) -> bool:
        """Return True when the full message queue is finished."""
        if not self.active:
            return True
        if self.reveal < len(self.current):
            self.reveal = float(len(self.current))
            return False
        if self.messages:
            self.current = self.messages.pop(0)
            self.reveal = 0.0
            return False
        self.active = False
        return True

    def draw(self, surface: pygame.Surface) -> None:
        if not self.active:
            return
        rect = pygame.Rect(6, LOGICAL_H - 44, LOGICAL_W - 12, 38)
        draw_window(surface, rect)
        visible = self.current[: int(self.reveal)]
        lines = wrap_text(self.font, visible, rect.width - 16)
        for i, line in enumerate(lines[:3]):
            draw_text(surface, self.font, line, rect.x + 8, rect.y + 7 + i * 10)
        if self.reveal >= len(self.current):
            blink = (pygame.time.get_ticks() // 260) % 2 == 0
            if blink:
                draw_text(surface, self.font, "▶", rect.right - 16, rect.bottom - 15)



# -----------------------------------------------------------------------------
# Procedural OST: single-file, no external audio assets
# -----------------------------------------------------------------------------


class RetroOST:
    """Tiny procedural chiptune music player using pygame.mixer.Sound buffers.

    The songs are original square-wave/noise loops designed for a retro handheld
    monster-RPG mood. They avoid external WAV/MP3 files and keep the whole game
    in one Python file.
    """

    NOTE_INDEX = {
        "C": 0,
        "C#": 1,
        "D": 2,
        "D#": 3,
        "E": 4,
        "F": 5,
        "F#": 6,
        "G": 7,
        "G#": 8,
        "A": 9,
        "A#": 10,
        "B": 11,
    }

    def __init__(self) -> None:
        self.enabled = pygame.mixer.get_init() is not None
        self.channel: Optional[pygame.mixer.Channel] = None
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.current_track = ""
        if not self.enabled:
            return
        try:
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            self.channel = pygame.mixer.Channel(0)
            self.sounds["field"] = self.make_field_theme()
            self.sounds["boss"] = self.make_professor_boss_theme()
            self.sounds["field"].set_volume(0.24)
            self.sounds["boss"].set_volume(0.34)
        except (pygame.error, ValueError):
            self.enabled = False
            self.channel = None
            self.sounds = {}

    def note_freq(self, note: Optional[str]) -> float:
        if note is None or note == "-":
            return 0.0
        name = note[:-1]
        octave = int(note[-1])
        midi = (octave + 1) * 12 + self.NOTE_INDEX[name]
        return 440.0 * (2.0 ** ((midi - 69) / 12.0))

    def square(self, phase: float, duty: float = 0.5) -> float:
        return 1.0 if (phase % 1.0) < duty else -1.0

    def triangle(self, phase: float) -> float:
        phase = phase % 1.0
        return 4.0 * abs(phase - 0.5) - 1.0

    def pseudo_noise(self, sample_index: int) -> float:
        # Deterministic hash-noise: crunchy percussion without importing assets.
        x = math.sin(sample_index * 12.9898 + 78.233) * 43758.5453
        return 2.0 * (x - math.floor(x)) - 1.0

    def envelope(self, pos: float, attack: float = 0.035, release: float = 0.22) -> float:
        # pos is 0..1 inside a sequencer step.
        if pos < attack:
            return pos / max(0.0001, attack)
        if pos > 1.0 - release:
            return max(0.0, (1.0 - pos) / max(0.0001, release))
        return 1.0

    def append_sample(self, samples: "array", value: float) -> None:
        value = max(-1.0, min(1.0, value))
        samples.append(int(value * 32767))

    def sound_from_samples(self, samples: "array") -> pygame.mixer.Sound:
        if sys.byteorder == "big":
            samples.byteswap()
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def make_field_theme(self) -> pygame.mixer.Sound:
        from array import array

        bpm = 128
        step = 60.0 / bpm / 2.0  # eighth-note grid
        steps = 32
        total_samples = int(AUDIO_SAMPLE_RATE * step * steps)
        samples = array("h")

        melody = [
            "E4", "G4", "A4", "B4", "A4", "G4", "E4", "-",
            "D4", "E4", "G4", "A4", "G4", "E4", "D4", "-",
            "C4", "E4", "G4", "A4", "B4", "A4", "G4", "E4",
            "D4", "F4", "A4", "G4", "E4", "D4", "C4", "-",
        ]
        bass = [
            "C2", "-", "G2", "-", "A2", "-", "E2", "-",
            "F2", "-", "C2", "-", "G2", "-", "G2", "-",
            "C2", "-", "G2", "-", "A2", "-", "E2", "-",
            "F2", "-", "C2", "-", "G2", "-", "C2", "-",
        ]

        lead_phase = 0.0
        bass_phase = 0.0
        for i in range(total_samples):
            t = i / AUDIO_SAMPLE_RATE
            idx = int(t / step) % steps
            pos = (t % step) / step
            mix = 0.0

            lead_freq = self.note_freq(melody[idx])
            if lead_freq:
                lead_phase += lead_freq / AUDIO_SAMPLE_RATE
                mix += 0.15 * self.square(lead_phase, 0.35) * self.envelope(pos, 0.05, 0.35)

            bass_freq = self.note_freq(bass[idx])
            if bass_freq:
                bass_phase += bass_freq / AUDIO_SAMPLE_RATE
                mix += 0.13 * self.triangle(bass_phase) * self.envelope(pos, 0.04, 0.25)

            # Very light click-hat so the field loop feels alive without crowding the battle track.
            if idx % 4 == 2 and pos < 0.18:
                mix += 0.025 * self.pseudo_noise(i) * math.exp(-22.0 * pos)

            self.append_sample(samples, mix)
        return self.sound_from_samples(samples)

    def make_professor_boss_theme(self) -> pygame.mixer.Sound:
        from array import array

        bpm = 172
        step = 60.0 / bpm / 4.0  # sixteenth-note grid
        steps = 96
        total_samples = int(AUDIO_SAMPLE_RATE * step * steps)
        samples = array("h")

        # Original energetic indie-retro boss loop: jumpy motif, minor tension,
        # square lead, quick arps, pulse bass, and crunchy fake drums.
        lead = [
            "E5", "-", "E5", "G5", "B5", "-", "A5", "G5",
            "E5", "-", "D5", "E5", "G5", "-", "E5", "D5",
            "C5", "-", "C5", "E5", "G5", "-", "A5", "G5",
            "B4", "-", "C5", "D5", "E5", "-", "D5", "B4",
            "E5", "-", "G5", "B5", "C6", "-", "B5", "G5",
            "A5", "-", "G5", "E5", "D5", "-", "E5", "G5",
            "C5", "-", "E5", "G5", "A5", "-", "G5", "E5",
            "D5", "-", "E5", "G5", "B5", "-", "A5", "G5",
            "E5", "G5", "E6", "D6", "B5", "G5", "A5", "B5",
            "C6", "B5", "A5", "G5", "E5", "G5", "A5", "B5",
            "E6", "-", "D6", "B5", "C6", "-", "B5", "A5",
            "G5", "E5", "D5", "E5", "G5", "A5", "B5", "D6",
        ]
        bass_roots = [
            "E2", "E2", "E2", "E2", "E2", "E2", "E2", "E2",
            "D2", "D2", "D2", "D2", "D2", "D2", "D2", "D2",
            "C2", "C2", "C2", "C2", "C2", "C2", "C2", "C2",
            "B1", "B1", "B1", "B1", "B1", "B1", "B1", "B1",
        ]
        arp_notes = [
            "E4", "G4", "B4", "D5", "E5", "D5", "B4", "G4",
            "D4", "F4", "A4", "C5", "D5", "C5", "A4", "F4",
            "C4", "E4", "G4", "B4", "C5", "B4", "G4", "E4",
            "B3", "D4", "F4", "A4", "B4", "A4", "F4", "D4",
        ]

        lead_phase = 0.0
        harmony_phase = 0.0
        bass_phase = 0.0
        arp_phase = 0.0
        for i in range(total_samples):
            t = i / AUDIO_SAMPLE_RATE
            idx = int(t / step) % steps
            pos = (t % step) / step
            phrase_idx = idx % 32
            mix = 0.0

            lead_freq = self.note_freq(lead[idx % len(lead)])
            if lead_freq:
                # Tiny vibrato gives the lead a handmade boss-theme wobble.
                wobble = 1.0 + 0.006 * math.sin(2.0 * math.pi * 6.0 * t)
                lead_phase += (lead_freq * wobble) / AUDIO_SAMPLE_RATE
                harmony_phase += (lead_freq * 0.5) / AUDIO_SAMPLE_RATE
                env = self.envelope(pos, 0.025, 0.18)
                mix += 0.19 * self.square(lead_phase, 0.25) * env
                mix += 0.06 * self.square(harmony_phase, 0.50) * env

            bass_freq = self.note_freq(bass_roots[phrase_idx])
            if bass_freq:
                # Alternating octave punches mimic old handheld pulse channels.
                octave = 2.0 if phrase_idx in {6, 7, 14, 15, 22, 23, 30, 31} else 1.0
                bass_phase += (bass_freq * octave) / AUDIO_SAMPLE_RATE
                mix += 0.22 * self.square(bass_phase, 0.50) * self.envelope(pos, 0.02, 0.12)

            arp_freq = self.note_freq(arp_notes[phrase_idx])
            if arp_freq:
                arp_phase += arp_freq / AUDIO_SAMPLE_RATE
                mix += 0.085 * self.square(arp_phase, 0.18) * self.envelope(pos, 0.015, 0.10)

            # Drum voices are synthesized from sine/noise bursts.
            beat = phrase_idx % 16
            if beat in {0, 8} and pos < 0.55:
                kick_t = pos * step
                kick_freq = 94.0 - 52.0 * pos
                mix += 0.25 * math.sin(2.0 * math.pi * kick_freq * kick_t) * math.exp(-8.5 * pos)
            if beat in {4, 12} and pos < 0.45:
                mix += 0.13 * self.pseudo_noise(i) * math.exp(-9.0 * pos)
            if beat in {2, 6, 10, 14} and pos < 0.23:
                mix += 0.055 * self.pseudo_noise(i + 991) * math.exp(-18.0 * pos)

            # A little master saturation keeps the boss loop loud without clipping harshly.
            mix = math.tanh(mix * 1.25) * 0.82
            self.append_sample(samples, mix)
        return self.sound_from_samples(samples)

    def play(self, track: str) -> None:
        if not self.enabled or self.channel is None:
            return
        sound = self.sounds.get(track)
        if sound is None:
            return
        if self.current_track == track and self.channel.get_busy():
            return
        self.channel.stop()
        self.channel.play(sound, loops=-1)
        self.current_track = track

    def play_field(self) -> None:
        self.play("field")

    def play_boss(self) -> None:
        self.play("boss")

    def stop(self) -> None:
        if self.channel is not None:
            self.channel.stop()
        self.current_track = ""



# -----------------------------------------------------------------------------
# Procedural SFX: menu clicks, battle hits, healing, saving, and NPC attacks
# -----------------------------------------------------------------------------


class RetroSFX:
    """Short procedural sound effects layered over the music channel.

    Channel 0 is reserved for RetroOST. These effects use channels 1+ so menu
    bleeps, professor attacks, item sounds, and battle feedback can overlap the
    boss theme without needing any external sound files.
    """

    def __init__(self) -> None:
        self.enabled = pygame.mixer.get_init() is not None
        self.channels: List[pygame.mixer.Channel] = []
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.channel_cursor = 0
        if not self.enabled:
            return
        try:
            channel_count = max(12, pygame.mixer.get_num_channels())
            pygame.mixer.set_num_channels(channel_count)
            self.channels = [pygame.mixer.Channel(i) for i in range(1, min(channel_count, 12))]
            if not self.channels:
                self.enabled = False
                return
            self.build_library()
        except (pygame.error, ValueError):
            self.enabled = False
            self.channels = []
            self.sounds = {}

    def append_sample(self, samples: "array", value: float) -> None:
        value = max(-1.0, min(1.0, value))
        samples.append(int(value * 32767))

    def sound_from_samples(self, samples: "array") -> pygame.mixer.Sound:
        if sys.byteorder == "big":
            samples.byteswap()
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def square(self, phase: float, duty: float = 0.5) -> float:
        return 1.0 if (phase % 1.0) < duty else -1.0

    def triangle(self, phase: float) -> float:
        phase = phase % 1.0
        return 4.0 * abs(phase - 0.5) - 1.0

    def pseudo_noise(self, sample_index: int, salt: int = 0) -> float:
        x = math.sin((sample_index + salt * 101) * 12.9898 + 78.233 + salt) * 43758.5453
        return 2.0 * (x - math.floor(x)) - 1.0

    def wave_sample(self, wave: str, phase: float, duty: float, sample_index: int, salt: int) -> float:
        if wave == "sine":
            return math.sin(2.0 * math.pi * phase)
        if wave == "triangle":
            return self.triangle(phase)
        if wave == "noise":
            return self.pseudo_noise(sample_index, salt)
        return self.square(phase, duty)

    def make_tone(
        self,
        duration: float,
        f0: float,
        f1: Optional[float] = None,
        *,
        volume: float = 0.35,
        wave: str = "square",
        duty: float = 0.5,
        noise: float = 0.0,
        attack: float = 0.08,
        decay: float = 5.0,
        vibrato: float = 0.0,
        bend_curve: float = 1.0,
        salt: int = 0,
    ) -> pygame.mixer.Sound:
        from array import array

        f1 = f0 if f1 is None else f1
        total_samples = max(1, int(AUDIO_SAMPLE_RATE * duration))
        samples = array("h")
        phase = 0.0
        for i in range(total_samples):
            p = i / max(1, total_samples - 1)
            freq = f0 + (f1 - f0) * (p ** bend_curve)
            if vibrato:
                freq *= 1.0 + vibrato * math.sin(2.0 * math.pi * 8.0 * (i / AUDIO_SAMPLE_RATE))
            phase += freq / AUDIO_SAMPLE_RATE
            env = min(1.0, p / max(0.0001, attack)) * math.exp(-decay * p)
            wave_value = self.wave_sample(wave, phase, duty, i, salt)
            value = wave_value * env * volume
            if noise:
                value += self.pseudo_noise(i, salt + 17) * env * noise
            self.append_sample(samples, math.tanh(value * 1.35))
        return self.sound_from_samples(samples)

    def make_arpeggio(
        self,
        freqs: Sequence[float],
        duration: float,
        *,
        volume: float = 0.32,
        wave: str = "square",
        duty: float = 0.35,
        salt: int = 0,
    ) -> pygame.mixer.Sound:
        from array import array

        total_samples = max(1, int(AUDIO_SAMPLE_RATE * duration))
        samples = array("h")
        phase = 0.0
        step = max(1, total_samples // max(1, len(freqs)))
        for i in range(total_samples):
            note_idx = min(len(freqs) - 1, i // step)
            local = (i % step) / max(1, step - 1)
            global_p = i / max(1, total_samples - 1)
            freq = freqs[note_idx] * (1.0 + 0.004 * math.sin(2.0 * math.pi * 9.0 * i / AUDIO_SAMPLE_RATE))
            phase += freq / AUDIO_SAMPLE_RATE
            env = min(1.0, local / 0.08) * math.exp(-3.4 * local) * (1.0 - 0.25 * global_p)
            primary = self.wave_sample(wave, phase, duty, i, salt)
            bell = math.sin(2.0 * math.pi * phase * 2.0) * 0.22
            self.append_sample(samples, (primary + bell) * env * volume)
        return self.sound_from_samples(samples)

    def make_heal(self) -> pygame.mixer.Sound:
        from array import array

        total_samples = int(AUDIO_SAMPLE_RATE * 0.85)
        samples = array("h")
        freqs = [523.25, 659.25, 783.99, 1046.50, 1318.51]
        phases = [0.0 for _ in freqs]
        for i in range(total_samples):
            p = i / max(1, total_samples - 1)
            shimmer = 0.0
            for j, freq in enumerate(freqs):
                gate = 0.5 + 0.5 * math.sin(2.0 * math.pi * (2.0 + j * 0.75) * p + j)
                phases[j] += freq / AUDIO_SAMPLE_RATE
                shimmer += math.sin(2.0 * math.pi * phases[j]) * gate * 0.055
            sparkle = self.pseudo_noise(i, 43) * 0.015 * (1.0 - p)
            env = min(1.0, p / 0.06) * math.sin(math.pi * p)
            self.append_sample(samples, (shimmer + sparkle) * env)
        return self.sound_from_samples(samples)

    def make_battle_start(self) -> pygame.mixer.Sound:
        from array import array

        total_samples = int(AUDIO_SAMPLE_RATE * 0.9)
        samples = array("h")
        lead_phase = 0.0
        low_phase = 0.0
        for i in range(total_samples):
            p = i / max(1, total_samples - 1)
            t = i / AUDIO_SAMPLE_RATE
            lead_freq = 220.0 + 660.0 * (p ** 0.65)
            low_freq = 92.0 - 35.0 * p
            lead_phase += lead_freq / AUDIO_SAMPLE_RATE
            low_phase += low_freq / AUDIO_SAMPLE_RATE
            stutter = 1.0 if int(p * 32) % 2 == 0 else 0.45
            sweep = self.square(lead_phase, 0.22) * math.exp(-1.7 * p) * stutter * 0.17
            drum = math.sin(2.0 * math.pi * low_phase) * math.exp(-8.0 * (p % 0.25)) * 0.18
            noise = self.pseudo_noise(i, 71) * 0.04 * math.exp(-3.0 * p)
            self.append_sample(samples, math.tanh((sweep + drum + noise) * 1.2))
        return self.sound_from_samples(samples)

    def make_hit(self, *, heavy: bool = False, salt: int = 0) -> pygame.mixer.Sound:
        from array import array

        duration = 0.18 if not heavy else 0.28
        total_samples = int(AUDIO_SAMPLE_RATE * duration)
        samples = array("h")
        phase = 0.0
        for i in range(total_samples):
            p = i / max(1, total_samples - 1)
            freq = (180.0 if heavy else 240.0) - (95.0 if heavy else 110.0) * p
            phase += freq / AUDIO_SAMPLE_RATE
            thump = math.sin(2.0 * math.pi * phase) * math.exp(-(11.0 if heavy else 15.0) * p)
            crack = self.pseudo_noise(i, salt) * math.exp(-24.0 * p)
            volume = 0.42 if heavy else 0.30
            self.append_sample(samples, math.tanh((thump * 0.75 + crack * 0.35) * volume * 2.0))
        return self.sound_from_samples(samples)

    def build_library(self) -> None:
        self.sounds = {
            "cursor": self.make_tone(0.045, 860, 1260, volume=0.20, wave="square", duty=0.25, decay=8.0, salt=1),
            "confirm": self.make_arpeggio([740, 988], 0.105, volume=0.23, duty=0.28, salt=2),
            "cancel": self.make_tone(0.10, 620, 260, volume=0.22, wave="triangle", decay=5.0, salt=3),
            "menu_open": self.make_arpeggio([523.25, 659.25, 783.99], 0.18, volume=0.20, duty=0.30, salt=4),
            "menu_close": self.make_arpeggio([783.99, 659.25, 523.25], 0.18, volume=0.19, duty=0.30, salt=5),
            "dialog": self.make_tone(0.035, 1180, 970, volume=0.12, wave="square", duty=0.18, decay=7.0, salt=6),
            "error": self.make_tone(0.19, 130, 118, volume=0.30, wave="square", duty=0.62, noise=0.04, decay=2.2, vibrato=0.018, salt=7),
            "save": self.make_arpeggio([392.00, 523.25, 783.99, 1046.50], 0.46, volume=0.23, duty=0.25, salt=8),
            "heal": self.make_heal(),
            "item": self.make_arpeggio([587.33, 880.00, 1174.66], 0.24, volume=0.21, duty=0.24, salt=9),
            "switch": self.make_tone(0.22, 340, 920, volume=0.22, wave="triangle", decay=3.8, vibrato=0.01, salt=10),
            "battle_start": self.make_battle_start(),
            "player_attack": self.make_tone(0.15, 720, 340, volume=0.30, wave="square", duty=0.22, noise=0.015, decay=5.0, salt=11),
            "enemy_attack": self.make_tone(0.20, 190, 520, volume=0.33, wave="square", duty=0.70, noise=0.060, decay=3.6, vibrato=0.012, salt=12),
            "hit": self.make_hit(heavy=False, salt=13),
            "hurt": self.make_hit(heavy=True, salt=14),
            "crit": self.make_arpeggio([880.00, 1174.66, 1567.98], 0.23, volume=0.28, duty=0.20, salt=15),
            "miss": self.make_tone(0.16, 900, 180, volume=0.18, wave="triangle", decay=5.2, salt=16),
            "status": self.make_arpeggio([440.00, 554.37, 659.25], 0.21, volume=0.20, duty=0.38, salt=17),
            "faint": self.make_tone(0.55, 420, 74, volume=0.24, wave="triangle", noise=0.015, decay=2.0, salt=18),
            "victory": self.make_arpeggio([523.25, 659.25, 783.99, 1046.50, 1318.51], 0.64, volume=0.25, duty=0.25, salt=19),
            "defeat": self.make_arpeggio([329.63, 261.63, 196.00, 130.81], 0.70, volume=0.22, duty=0.42, salt=20),
        }
        for name, sound in self.sounds.items():
            if name in {"enemy_attack", "battle_start", "hurt"}:
                sound.set_volume(0.62)
            elif name in {"heal", "victory", "defeat", "save"}:
                sound.set_volume(0.58)
            else:
                sound.set_volume(0.50)

    def play(self, name: str, *, volume: Optional[float] = None) -> None:
        if not self.enabled or not self.channels:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            channel = self.channels[self.channel_cursor % len(self.channels)]
            self.channel_cursor += 1
            if volume is not None:
                channel.set_volume(volume)
            else:
                channel.set_volume(1.0)
            channel.play(sound)
        except pygame.error:
            return


# -----------------------------------------------------------------------------
# Main game class
# -----------------------------------------------------------------------------


class Game:
    def __init__(self) -> None:
        pygame.mixer.pre_init(AUDIO_SAMPLE_RATE, -16, 1, AUDIO_BUFFER_SIZE)
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self.window = pygame.display.set_mode((LOGICAL_W * SCALE, LOGICAL_H * SCALE))
        self.canvas = pygame.Surface((LOGICAL_W, LOGICAL_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 14)
        self.small_font = pygame.font.Font(None, 12)
        self.big_font = pygame.font.Font(None, 24)
        self.textbox = TextBox(self.font)
        self.ost = RetroOST()
        self.sfx = RetroSFX()

        # Simple 15x10 tile map. H is a heal/save-point tile. T is blocked.
        self.map_rows = [
            "TTTTTTTTTTTTTTT",
            "T.............T",
            "T..GGG...GGG..T",
            "T..G.......G..T",
            "T.....HH......T",
            "T.............T",
            "T...TTT.......T",
            "T.............T",
            "T.............T",
            "TTTTTTTTTTTTTTT",
        ]

        self.state = "title"
        self.dialog_base_state = "overworld"
        self.dialog_return_state = "overworld"
        self.dialog_after: Optional[Callable[[], None]] = None

        self.save_path = self.default_save_path()
        self.title_items: List[str] = []
        self.title_index = 0

        self.pause_items = ["PARTY", "BAG", "TRAINER", "SAVE", "OPTIONS", "CLOSE"]
        self.pause_index = 0
        self.party_index = 0
        self.bag_index = 0
        self.option_index = 0
        self.text_speed_label = "FAST"
        self.battle_style_label = "SET"

        self.player_px = 3 * TILE
        self.player_py = 7 * TILE
        self.player_dir = "down"
        self.moving = False
        self.move_target = (self.player_px, self.player_py)
        self.move_dir = (0, 0)
        self.last_heal_tile: Optional[Tuple[int, int]] = None

        self.prof_pos = (10, 3)
        self.prof_defeated = False

        self.inventory = {"POTION": 3, "GUIDE": 1}
        self.player_party: List[Monster] = []
        self.enemy_party: List[Monster] = []
        self.player_active_idx = 0
        self.enemy_active_idx = 0
        self.battle_menu_index = 0
        self.move_index = 0
        self.battle_bag_index = 0
        self.battle_party_index = 0
        self.battle_flash_timer = 0
        self.battle_turn_note = ""

        self.reset_game_data()
        self.refresh_title_items()
        self.ost.play_field()

    # ---------------------------------------------------------------------
    # Data setup
    # ---------------------------------------------------------------------

    def reset_game_data(self) -> None:
        self.player_party = [
            Monster(
                "SPRIGIT",
                10,
                42,
                17,
                13,
                15,
                [
                    Move("TACKLE", 38, 0.95, 35),
                    Move("LEAF TAP", 44, 0.95, 25),
                    Move("QUICK NIP", 32, 1.00, 30),
                    Move("FOCUS", 0, 1.00, 20),
                ],
            ),
            Monster(
                "EMBERKIT",
                8,
                36,
                18,
                11,
                13,
                [
                    Move("SCRATCH", 36, 1.00, 35),
                    Move("SPARK ASH", 42, 0.90, 25),
                    Move("TAIL WAVE", 0, 1.00, 30),
                    Move("NIBBLE", 30, 1.00, 35),
                ],
            ),
            Monster(
                "AQUABIT",
                7,
                39,
                14,
                15,
                10,
                [
                    Move("BUMP", 35, 1.00, 35),
                    Move("BUBBLE POP", 40, 0.95, 30),
                    Move("GUARD", 0, 1.00, 20),
                    Move("SPLASHY HIT", 32, 1.00, 30),
                ],
            ),
        ]
        self.inventory = {"POTION": 3, "GUIDE": 1}
        self.enemy_party = []
        self.player_active_idx = 0
        self.enemy_active_idx = 0
        self.battle_menu_index = 0
        self.move_index = 0
        self.battle_bag_index = 0
        self.battle_party_index = 0
        self.player_px = 3 * TILE
        self.player_py = 7 * TILE
        self.player_dir = "down"
        self.moving = False
        self.move_target = (self.player_px, self.player_py)
        self.prof_defeated = False
        self.last_heal_tile = None

    def make_enemy_party(self) -> List[Monster]:
        return [
            Monster(
                "ACORNIX",
                11,
                44,
                16,
                15,
                12,
                [
                    Move("RAM", 36, 1.00, 35),
                    Move("ROOT SNAG", 42, 0.95, 25),
                    Move("BARK UP", 0, 1.00, 25),
                    Move("SEED SHOT", 45, 0.90, 20),
                ],
            ),
            Monster(
                "LECTROBUD",
                12,
                40,
                19,
                12,
                17,
                [
                    Move("JOLT", 45, 0.90, 25),
                    Move("QUICK NIP", 32, 1.00, 30),
                    Move("STATIC TAP", 38, 0.95, 25),
                    Move("GLARE", 0, 1.00, 20),
                ],
            ),
        ]

    # ---------------------------------------------------------------------
    # Save / load support
    # ---------------------------------------------------------------------

    def default_save_path(self) -> Path:
        try:
            return Path(__file__).resolve().with_name(SAVE_FILE_NAME)
        except NameError:
            return Path.cwd() / SAVE_FILE_NAME

    def save_exists(self) -> bool:
        return self.save_path.exists()

    def refresh_title_items(self) -> None:
        items = ["NEW GAME", "CONTROLS", "QUIT"]
        if self.save_exists():
            items.insert(0, "CONTINUE")
        self.title_items = items
        self.title_index = min(self.title_index, len(self.title_items) - 1)

    def move_to_save(self, move: Move) -> Dict[str, Any]:
        return {
            "name": move.name,
            "power": move.power,
            "accuracy": move.accuracy,
            "max_pp": move.max_pp,
            "pp": move.pp,
        }

    def monster_to_save(self, monster: Monster) -> Dict[str, Any]:
        return {
            "name": monster.name,
            "level": monster.level,
            "max_hp": monster.max_hp,
            "attack": monster.attack,
            "defense": monster.defense,
            "speed": monster.speed,
            "hp": monster.hp,
            "moves": [self.move_to_save(move) for move in monster.moves],
        }

    def save_payload(self) -> Dict[str, Any]:
        return {
            "version": SAVE_SCHEMA_VERSION,
            "player": {
                "x": self.player_px,
                "y": self.player_py,
                "dir": self.player_dir,
            },
            "prof_defeated": self.prof_defeated,
            "inventory": dict(self.inventory),
            "party": [self.monster_to_save(monster) for monster in self.player_party],
            "player_active_idx": self.player_active_idx,
            "options": {
                "text_speed": self.text_speed_label,
                "battle_style": self.battle_style_label,
            },
        }

    def save_game(self) -> Tuple[bool, str]:
        payload = self.save_payload()
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.save_path.with_suffix(self.save_path.suffix + ".tmp")
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            tmp_path.replace(self.save_path)
            self.refresh_title_items()
            return True, f"Progress written to {SAVE_FILE_NAME}."
        except OSError as exc:
            return False, f"Save failed: {exc}"

    def loaded_move(self, data: Any, fallback: Move) -> Move:
        if not isinstance(data, dict):
            data = {}
        move = Move(
            str(data.get("name", fallback.name)),
            int(data.get("power", fallback.power)),
            float(data.get("accuracy", fallback.accuracy)),
            max(1, int(data.get("max_pp", fallback.max_pp))),
        )
        move.pp = clamp(int(data.get("pp", fallback.pp)), 0, move.max_pp)
        return move

    def loaded_monster(self, data: Any, fallback: Monster) -> Monster:
        if not isinstance(data, dict):
            data = {}
        saved_moves = data.get("moves", [])
        if not isinstance(saved_moves, list):
            saved_moves = []
        moves = []
        for idx, fallback_move in enumerate(fallback.moves):
            move_data = saved_moves[idx] if idx < len(saved_moves) else {}
            moves.append(self.loaded_move(move_data, fallback_move))
        monster = Monster(
            str(data.get("name", fallback.name)),
            int(data.get("level", fallback.level)),
            max(1, int(data.get("max_hp", fallback.max_hp))),
            max(1, int(data.get("attack", fallback.attack))),
            max(1, int(data.get("defense", fallback.defense))),
            max(1, int(data.get("speed", fallback.speed))),
            moves,
        )
        monster.hp = clamp(int(data.get("hp", fallback.hp)), 0, monster.max_hp)
        return monster

    def load_game(self) -> Tuple[bool, str]:
        if not self.save_exists():
            return False, "No save file was found."
        try:
            with self.save_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("save root is not an object")
            if int(data.get("version", -1)) != SAVE_SCHEMA_VERSION:
                raise ValueError("save version is not supported")

            self.reset_game_data()
            fallback_party = list(self.player_party)
            self.prof_defeated = bool(data.get("prof_defeated", False))

            player = data.get("player", {})
            if not isinstance(player, dict):
                player = {}
            loaded_x = clamp(int(player.get("x", self.player_px)), TILE, (len(self.map_rows[0]) - 2) * TILE)
            loaded_y = clamp(int(player.get("y", self.player_py)), TILE, (len(self.map_rows) - 2) * TILE)
            self.player_px = int(round(loaded_x / TILE)) * TILE
            self.player_py = int(round(loaded_y / TILE)) * TILE
            self.move_target = (self.player_px, self.player_py)
            self.player_dir = str(player.get("dir", "down")) if player.get("dir", "down") in DIRS else "down"
            if self.is_blocked(*self.player_tile):
                self.player_px = 3 * TILE
                self.player_py = 7 * TILE
                self.move_target = (self.player_px, self.player_py)


            saved_inventory = data.get("inventory", {})
            if not isinstance(saved_inventory, dict):
                saved_inventory = {}
            self.inventory = {
                "POTION": max(0, int(saved_inventory.get("POTION", self.inventory.get("POTION", 0)))),
                "GUIDE": max(0, int(saved_inventory.get("GUIDE", self.inventory.get("GUIDE", 1)))),
            }

            saved_party = data.get("party", [])
            if not isinstance(saved_party, list):
                saved_party = []
            self.player_party = []
            for idx, fallback_monster in enumerate(fallback_party):
                monster_data = saved_party[idx] if idx < len(saved_party) else {}
                self.player_party.append(self.loaded_monster(monster_data, fallback_monster))
            if not any(not monster.fainted for monster in self.player_party):
                self.heal_party()
            self.player_active_idx = clamp(int(data.get("player_active_idx", 0)), 0, len(self.player_party) - 1)
            if self.active_player.fainted:
                first_alive = self.first_alive_player_idx()
                self.player_active_idx = first_alive if first_alive is not None else 0

            options = data.get("options", {})
            if not isinstance(options, dict):
                options = {}
            text_speed = str(options.get("text_speed", self.text_speed_label))
            battle_style = str(options.get("battle_style", self.battle_style_label))
            self.text_speed_label = text_speed if text_speed in {"FAST", "MID"} else "FAST"
            self.battle_style_label = battle_style if battle_style in {"SET", "SHIFT"} else "SET"
            self.sync_text_speed()

            self.enemy_party = []
            self.enemy_active_idx = 0
            self.moving = False
            self.last_heal_tile = None
            self.state = "overworld"
            return True, f"Loaded {SAVE_FILE_NAME}."
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.reset_game_data()
            self.state = "title"
            return False, f"Load failed: {exc}"

    def save_after_heal(self) -> List[str]:
        ok, message = self.save_game()
        self.sfx.play("save" if ok else "error")
        return ["Your party was fully healed.", message]

    def sync_text_speed(self) -> None:
        self.textbox.reveal_speed = TEXT_SPEEDS.get(self.text_speed_label, TEXT_REVEAL_SPEED)

    # ---------------------------------------------------------------------
    # Utility properties
    # ---------------------------------------------------------------------

    @property
    def player_tile(self) -> Tuple[int, int]:
        return int(round(self.player_px / TILE)), int(round(self.player_py / TILE))

    @property
    def active_player(self) -> Monster:
        return self.player_party[self.player_active_idx]

    @property
    def active_enemy(self) -> Monster:
        return self.enemy_party[self.enemy_active_idx]

    def first_alive_player_idx(self) -> Optional[int]:
        for i, monster in enumerate(self.player_party):
            if not monster.fainted:
                return i
        return None

    def first_alive_enemy_idx(self) -> Optional[int]:
        for i, monster in enumerate(self.enemy_party):
            if not monster.fainted:
                return i
        return None

    def tile_at(self, tx: int, ty: int) -> str:
        if ty < 0 or ty >= len(self.map_rows) or tx < 0 or tx >= len(self.map_rows[0]):
            return "T"
        return self.map_rows[ty][tx]

    def is_blocked(self, tx: int, ty: int) -> bool:
        if self.tile_at(tx, ty) == "T":
            return True
        if not self.prof_defeated and (tx, ty) == self.prof_pos:
            return True
        return False

    def facing_tile(self) -> Tuple[int, int]:
        tx, ty = self.player_tile
        dx, dy = DIRS[self.player_dir]
        return tx + dx, ty + dy

    def heal_party(self) -> None:
        for monster in self.player_party:
            monster.heal_full()

    # ---------------------------------------------------------------------
    # Dialog management
    # ---------------------------------------------------------------------

    def start_dialog(
        self,
        messages: Sequence[str],
        base_state: str = "overworld",
        return_state: str = "overworld",
        after: Optional[Callable[[], None]] = None,
    ) -> None:
        if hasattr(self, "sfx"):
            self.sfx.play("dialog")
        self.textbox.start(messages)
        self.dialog_base_state = base_state
        self.dialog_return_state = return_state
        self.dialog_after = after
        self.state = "dialog"

    def finish_dialog(self) -> None:
        after = self.dialog_after
        self.dialog_after = None
        if after is not None:
            after()
        else:
            self.state = self.dialog_return_state

    # ---------------------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------------------

    def run(self) -> None:
        while True:
            dt = self.clock.tick(FPS)
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.transform.scale(self.canvas, self.window.get_size(), self.window)
            pygame.display.flip()

    # ---------------------------------------------------------------------
    # Input
    # ---------------------------------------------------------------------

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                self.handle_keydown(event.key)

    def handle_keydown(self, key: int) -> None:
        if key in (pygame.K_z, pygame.K_RETURN, pygame.K_SPACE):
            self.sfx.play("dialog" if self.state == "dialog" else "confirm")
            self.confirm()
        elif key in (pygame.K_x, pygame.K_BACKSPACE):
            self.sfx.play("cancel")
            self.cancel()
        elif key in (pygame.K_UP, pygame.K_w):
            if self.cursor_move(-1, vertical=True):
                self.sfx.play("cursor")
        elif key in (pygame.K_DOWN, pygame.K_s):
            if self.cursor_move(1, vertical=True):
                self.sfx.play("cursor")
        elif key in (pygame.K_LEFT, pygame.K_a):
            if self.cursor_move(-1, vertical=False):
                self.sfx.play("cursor")
        elif key in (pygame.K_RIGHT, pygame.K_d):
            if self.cursor_move(1, vertical=False):
                self.sfx.play("cursor")
        elif key in (pygame.K_ESCAPE, pygame.K_m):
            if self.state == "overworld":
                self.sfx.play("menu_open")
                self.state = "pause"
            elif self.state in {"pause", "party", "bag", "trainer", "options"}:
                self.sfx.play("menu_close")
                self.state = "overworld"

    def confirm(self) -> None:
        if self.state == "title":
            self.title_confirm()
        elif self.state == "dialog":
            if self.textbox.advance():
                self.finish_dialog()
        elif self.state == "overworld":
            self.interact_overworld()
        elif self.state == "pause":
            self.pause_confirm()
        elif self.state == "party":
            self.party_confirm()
        elif self.state == "bag":
            self.bag_confirm()
        elif self.state == "trainer":
            self.state = "pause"
        elif self.state == "options":
            self.options_confirm()
        elif self.state == "battle_menu":
            self.battle_menu_confirm()
        elif self.state == "fight_menu":
            self.fight_confirm()
        elif self.state == "battle_bag":
            self.battle_bag_confirm()
        elif self.state == "battle_party":
            self.battle_party_confirm()

    def cancel(self) -> None:
        if self.state == "dialog":
            if self.textbox.reveal < len(self.textbox.current):
                self.textbox.reveal = len(self.textbox.current)
        elif self.state == "pause":
            self.state = "overworld"
        elif self.state in {"party", "bag", "trainer", "options"}:
            self.state = "pause"
        elif self.state in {"fight_menu", "battle_bag", "battle_party"}:
            self.state = "battle_menu"

    def move_grid_cursor(self, index: int, amount: int, vertical: bool) -> int:
        """Move a cursor around a 2x2 menu without wrapping diagonally."""
        if vertical:
            return (index + amount * 2) % 4
        row = index // 2
        col = (index % 2 + amount) % 2
        return row * 2 + col

    def cursor_move(self, amount: int, vertical: bool) -> bool:
        if self.state == "title" and vertical:
            self.title_index = (self.title_index + amount) % len(self.title_items)
            return True
        elif self.state == "pause" and vertical:
            self.pause_index = (self.pause_index + amount) % len(self.pause_items)
            return True
        elif self.state == "party" and vertical:
            self.party_index = (self.party_index + amount) % len(self.player_party)
            return True
        elif self.state == "bag" and vertical:
            items = self.bag_items()
            self.bag_index = (self.bag_index + amount) % len(items)
            return True
        elif self.state == "options" and vertical:
            self.option_index = (self.option_index + amount) % 3
            return True
        elif self.state == "battle_menu":
            self.battle_menu_index = self.move_grid_cursor(self.battle_menu_index, amount, vertical)
            return True
        elif self.state == "fight_menu":
            self.move_index = self.move_grid_cursor(self.move_index, amount, vertical)
            return True
        elif self.state == "battle_bag" and vertical:
            items = self.battle_bag_items()
            self.battle_bag_index = (self.battle_bag_index + amount) % len(items)
            return True
        elif self.state == "battle_party" and vertical:
            self.battle_party_index = (self.battle_party_index + amount) % len(self.player_party)
            return True
        return False

    # ---------------------------------------------------------------------
    # Update
    # ---------------------------------------------------------------------

    def update(self, dt_ms: int) -> None:
        _ = dt_ms
        if self.state == "overworld":
            self.update_overworld()
        elif self.state == "dialog":
            self.textbox.update()
        if self.battle_flash_timer > 0:
            self.battle_flash_timer -= 1

    def update_overworld(self) -> None:
        keys = pygame.key.get_pressed()
        if self.moving:
            tx, ty = self.move_target
            dx = clamp(tx - self.player_px, -PLAYER_SPEED, PLAYER_SPEED)
            dy = clamp(ty - self.player_py, -PLAYER_SPEED, PLAYER_SPEED)
            self.player_px += dx
            self.player_py += dy
            if self.player_px == tx and self.player_py == ty:
                self.moving = False
                self.check_heal_tile_step()
            return

        desired_dir: Optional[str] = None
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            desired_dir = "up"
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            desired_dir = "down"
        elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
            desired_dir = "left"
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            desired_dir = "right"

        if desired_dir:
            self.player_dir = desired_dir
            dx, dy = DIRS[desired_dir]
            tx, ty = self.player_tile
            nx, ny = tx + dx, ty + dy
            if not self.is_blocked(nx, ny):
                self.moving = True
                self.move_target = (nx * TILE, ny * TILE)

    def check_heal_tile_step(self) -> None:
        tx, ty = self.player_tile
        if self.tile_at(tx, ty) == "H" and self.last_heal_tile != (tx, ty):
            self.last_heal_tile = (tx, ty)
            self.sfx.play("heal")
            self.heal_party()
            self.start_dialog(
                ["HEAL/SAVE POINT glows warmly."] + self.save_after_heal(),
                base_state="overworld",
                return_state="overworld",
            )
        elif self.tile_at(tx, ty) != "H":
            self.last_heal_tile = None

    # ---------------------------------------------------------------------
    # Title / overworld / pause menus
    # ---------------------------------------------------------------------

    def title_confirm(self) -> None:
        self.refresh_title_items()
        item = self.title_items[self.title_index]
        if item == "CONTINUE":
            ok, message = self.load_game()
            if ok:
                self.ost.play_field()
                self.start_dialog(
                    [message, "Welcome back. Your saved progress is ready."],
                    base_state="overworld",
                    return_state="overworld",
                )
            else:
                self.refresh_title_items()
                self.start_dialog(
                    [message, "Start a NEW GAME or replace the save file."],
                    base_state="title",
                    return_state="title",
                )
        elif item == "NEW GAME":
            self.ost.play_field()
            self.reset_game_data()
            self.state = "overworld"
            self.start_dialog(
                [
                    "A tiny monster-battler demo begins.",
                    "Professor Alder is waiting by the north grass.",
                    "Walk onto the red pad to heal and save.",
                ],
                base_state="overworld",
                return_state="overworld",
            )
        elif item == "CONTROLS":
            self.start_dialog(
                [
                    "Move with Arrow keys or WASD.",
                    "Press Z, Enter, or Space to confirm/interact.",
                    "Press X or Backspace to cancel. Press Esc/M for the overworld menu.",
                ],
                base_state="title",
                return_state="title",
            )
        elif item == "QUIT":
            pygame.quit()
            sys.exit()

    def interact_overworld(self) -> None:
        tx, ty = self.facing_tile()
        px, py = self.player_tile
        if not self.prof_defeated and (tx, ty) == self.prof_pos:
            self.start_dialog(
                [
                    "PROF. ALDER: Ah, you found me.",
                    "This prototype includes an overworld, menus, healing, and a trainer battle.",
                    "Now show me your monster-handling skills!",
                ],
                base_state="overworld",
                return_state="overworld",
                after=self.begin_battle,
            )
        elif self.tile_at(tx, ty) == "H" or self.tile_at(px, py) == "H":
            self.sfx.play("heal")
            self.heal_party()
            self.start_dialog(
                ["The HEAL/SAVE POINT glows warmly."] + self.save_after_heal(),
                base_state="overworld",
                return_state="overworld",
            )
        else:
            self.sfx.play("error")
            self.start_dialog(
                ["There is nothing to use here."],
                base_state="overworld",
                return_state="overworld",
            )

    def pause_confirm(self) -> None:
        item = self.pause_items[self.pause_index]
        if item == "PARTY":
            self.sfx.play("menu_open")
            self.party_index = 0
            self.state = "party"
        elif item == "BAG":
            self.sfx.play("menu_open")
            self.bag_index = 0
            self.state = "bag"
        elif item == "TRAINER":
            self.sfx.play("menu_open")
            self.state = "trainer"
        elif item == "SAVE":
            ok, message = self.save_game()
            self.sfx.play("save" if ok else "error")
            lines = ["Game saved.", message] if ok else ["The game could not be saved.", message]
            self.start_dialog(
                lines,
                base_state="overworld",
                return_state="overworld",
            )
        elif item == "OPTIONS":
            self.sfx.play("menu_open")
            self.option_index = 0
            self.state = "options"
        elif item == "CLOSE":
            self.sfx.play("menu_close")
            self.state = "overworld"

    def party_confirm(self) -> None:
        monster = self.player_party[self.party_index]
        self.start_dialog(
            [
                f"{monster.name}: Lv {monster.level}, HP {monster.hp}/{monster.max_hp}.",
                "Switching is available during battle from the PARTY command.",
            ],
            base_state="overworld",
            return_state="party",
        )

    def bag_items(self) -> List[str]:
        return [f"{name} x{amount}" for name, amount in self.inventory.items()] + ["CLOSE"]

    def bag_confirm(self) -> None:
        items = self.bag_items()
        label = items[self.bag_index]
        if label == "CLOSE":
            self.sfx.play("menu_close")
            self.state = "pause"
            return
        if label.startswith("POTION"):
            self.sfx.play("item")
            self.start_dialog(
                ["POTION can be used during battle from the BAG command."],
                base_state="overworld",
                return_state="bag",
            )
        elif label.startswith("GUIDE"):
            self.sfx.play("item")
            self.start_dialog(
                [
                    "GUIDE: Find Professor Alder, battle him, and heal on the red pad.",
                    "Use MENU > SAVE or the red pad to save progress.",
                ],
                base_state="overworld",
                return_state="bag",
            )

    def options_confirm(self) -> None:
        if self.option_index == 0:
            self.text_speed_label = "MID" if self.text_speed_label == "FAST" else "FAST"
            self.sync_text_speed()
        elif self.option_index == 1:
            self.battle_style_label = "SHIFT" if self.battle_style_label == "SET" else "SET"
        elif self.option_index == 2:
            self.sfx.play("menu_close")
            self.state = "pause"

    # ---------------------------------------------------------------------
    # Battle setup and flow
    # ---------------------------------------------------------------------

    def begin_battle(self) -> None:
        self.sfx.play("battle_start")
        self.ost.play_boss()
        self.enemy_party = self.make_enemy_party()
        first_player = self.first_alive_player_idx()
        if first_player is None:
            self.heal_party()
            first_player = self.first_alive_player_idx()
        self.player_active_idx = first_player if first_player is not None else 0
        self.enemy_active_idx = 0
        self.battle_menu_index = 0
        self.move_index = 0
        self.battle_turn_note = ""
        self.start_dialog(
            [
                "PROF. ALDER wants to battle!",
                f"PROF. ALDER sent out {self.active_enemy.name}!",
                f"Go, {self.active_player.name}!",
            ],
            base_state="battle",
            return_state="battle_menu",
        )

    def battle_menu_confirm(self) -> None:
        commands = ["FIGHT", "BAG", "PARTY", "RUN"]
        command = commands[self.battle_menu_index]
        if command == "FIGHT":
            self.sfx.play("menu_open")
            self.move_index = 0
            self.state = "fight_menu"
        elif command == "BAG":
            self.sfx.play("menu_open")
            self.battle_bag_index = 0
            self.state = "battle_bag"
        elif command == "PARTY":
            self.sfx.play("menu_open")
            self.battle_party_index = 0
            self.state = "battle_party"
        elif command == "RUN":
            self.sfx.play("error")
            self.start_dialog(
                ["No running from a professor battle!"],
                base_state="battle",
                return_state="battle_menu",
            )

    def fight_confirm(self) -> None:
        move = self.active_player.moves[self.move_index]
        if move.pp <= 0:
            self.sfx.play("error")
            self.start_dialog(
                [f"There is no PP left for {move.name}!"],
                base_state="battle",
                return_state="fight_menu",
            )
            return
        self.player_uses_move(move)

    def battle_bag_items(self) -> List[str]:
        return ["POTION", "CLOSE"]

    def battle_bag_confirm(self) -> None:
        item = self.battle_bag_items()[self.battle_bag_index]
        if item == "CLOSE":
            self.sfx.play("menu_close")
            self.state = "battle_menu"
            return
        if item == "POTION":
            if self.inventory.get("POTION", 0) <= 0:
                self.sfx.play("error")
                self.start_dialog(["No POTION left!"], base_state="battle", return_state="battle_menu")
                return
            mon = self.active_player
            if mon.hp >= mon.max_hp:
                self.sfx.play("error")
                self.start_dialog([f"{mon.name} already has full HP."], base_state="battle", return_state="battle_bag")
                return
            self.sfx.play("item")
            self.sfx.play("heal")
            self.inventory["POTION"] -= 1
            healed = min(20, mon.max_hp - mon.hp)
            mon.hp += healed
            self.start_dialog(
                [f"You used POTION on {mon.name}.", f"{mon.name} recovered {healed} HP!"],
                base_state="battle",
                return_state="battle_menu",
                after=self.enemy_turn,
            )

    def battle_party_confirm(self) -> None:
        chosen = self.player_party[self.battle_party_index]
        if chosen.fainted:
            self.sfx.play("error")
            self.start_dialog([f"{chosen.name} has fainted."], base_state="battle", return_state="battle_party")
            return
        if self.battle_party_index == self.player_active_idx:
            self.sfx.play("error")
            self.start_dialog([f"{chosen.name} is already out."], base_state="battle", return_state="battle_party")
            return
        old = self.active_player
        self.sfx.play("switch")
        self.player_active_idx = self.battle_party_index
        new = self.active_player
        self.start_dialog(
            [f"Come back, {old.name}!", f"Go, {new.name}!"],
            base_state="battle",
            return_state="battle_menu",
            after=self.enemy_turn,
        )

    def calc_damage(self, attacker: Monster, defender: Monster, move: Move) -> Tuple[int, bool, bool]:
        if move.power <= 0:
            return 0, True, False
        if random.random() > move.accuracy:
            return 0, False, False
        base = (((2 * attacker.level / 5 + 2) * move.power * attacker.attack / max(1, defender.defense)) / 50) + 2
        crit = random.random() < 0.0625
        spread = random.uniform(0.85, 1.0)
        damage = max(1, int(base * spread * (2 if crit else 1)))
        return damage, True, crit

    def apply_status_move(self, attacker: Monster, defender: Monster, move: Move) -> List[str]:
        # Small original status system: non-damaging moves buff attack or defense.
        if move.name in {"FOCUS", "BARK UP"}:
            attacker.attack += 2
            return [f"{attacker.name}'s ATTACK rose!"]
        if move.name in {"GUARD"}:
            attacker.defense += 2
            return [f"{attacker.name}'s DEFENSE rose!"]
        if move.name in {"TAIL WAVE", "GLARE"}:
            defender.speed = max(1, defender.speed - 2)
            return [f"{defender.name}'s SPEED fell!"]
        return ["But nothing happened."]

    def player_uses_move(self, move: Move) -> None:
        attacker = self.active_player
        defender = self.active_enemy
        move.pp -= 1
        lines = [f"{attacker.name} used {move.name}!"]
        if move.power <= 0:
            self.sfx.play("status")
            lines.extend(self.apply_status_move(attacker, defender, move))
            self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.enemy_turn)
            return
        self.sfx.play("player_attack")
        damage, hit, crit = self.calc_damage(attacker, defender, move)
        if not hit:
            self.sfx.play("miss")
            lines.append("The attack missed!")
            self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.enemy_turn)
            return
        defender.hp = max(0, defender.hp - damage)
        self.battle_flash_timer = 12
        self.sfx.play("crit" if crit else "hit")
        if crit:
            lines.append("A critical hit!")
        lines.append(f"Enemy {defender.name} took {damage} damage!")
        if defender.fainted:
            self.sfx.play("faint")
            lines.append(f"Enemy {defender.name} fainted!")
            next_enemy = self.next_enemy_after_current()
            if next_enemy is None:
                self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.battle_win)
            else:
                self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.enemy_switch)
        else:
            self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.enemy_turn)

    def next_enemy_after_current(self) -> Optional[int]:
        for i, monster in enumerate(self.enemy_party):
            if not monster.fainted and i != self.enemy_active_idx:
                return i
        return None

    def enemy_switch(self) -> None:
        next_enemy = self.next_enemy_after_current()
        if next_enemy is None:
            self.battle_win()
            return
        self.enemy_active_idx = next_enemy
        self.sfx.play("switch")
        self.start_dialog(
            [f"PROF. ALDER sent out {self.active_enemy.name}!"],
            base_state="battle",
            return_state="battle_menu",
        )

    def enemy_turn(self) -> None:
        if self.active_enemy.fainted:
            self.enemy_switch()
            return
        enemy = self.active_enemy
        player = self.active_player
        usable_moves = [m for m in enemy.moves if m.pp > 0]
        move = random.choice(usable_moves) if usable_moves else enemy.moves[0]
        if move.pp > 0:
            move.pp -= 1
        lines = [f"Enemy {enemy.name} used {move.name}!"]
        if move.power <= 0:
            self.sfx.play("status")
            lines.extend(self.apply_status_move(enemy, player, move))
            self.start_dialog(lines, base_state="battle", return_state="battle_menu")
            return
        self.sfx.play("enemy_attack")
        damage, hit, crit = self.calc_damage(enemy, player, move)
        if not hit:
            self.sfx.play("miss")
            lines.append("The attack missed!")
            self.start_dialog(lines, base_state="battle", return_state="battle_menu")
            return
        player.hp = max(0, player.hp - damage)
        self.battle_flash_timer = 12
        self.sfx.play("crit" if crit else "hurt")
        if crit:
            lines.append("A critical hit!")
        lines.append(f"{player.name} took {damage} damage!")
        if player.fainted:
            self.sfx.play("faint")
            lines.append(f"{player.name} fainted!")
            next_player = self.first_alive_player_idx()
            if next_player is None:
                self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=self.battle_loss)
            else:
                self.start_dialog(lines, base_state="battle", return_state="battle_menu", after=lambda: self.auto_send_next(next_player))
        else:
            self.start_dialog(lines, base_state="battle", return_state="battle_menu")

    def auto_send_next(self, idx: int) -> None:
        self.sfx.play("switch")
        self.player_active_idx = idx
        self.start_dialog([f"Go, {self.active_player.name}!"], base_state="battle", return_state="battle_menu")

    def battle_win(self) -> None:
        self.sfx.play("victory")
        self.prof_defeated = True
        self.start_dialog(
            [
                "PLAYER defeated PROF. ALDER!",
                "PROF. ALDER: Excellent! This proves the core battle loop works.",
                "Your party will be healed. Save from the menu or the red pad.",
            ],
            base_state="battle",
            return_state="overworld",
            after=self.finish_battle_win,
        )

    def finish_battle_win(self) -> None:
        self.ost.play_field()
        self.sfx.play("heal")
        self.heal_party()
        self.state = "overworld"
        self.start_dialog(
            ["The field is calm again. Your party was healed."],
            base_state="overworld",
            return_state="overworld",
        )

    def battle_loss(self) -> None:
        self.ost.play_field()
        self.sfx.play("defeat")
        self.heal_party()
        self.player_active_idx = 0
        self.player_px = 6 * TILE
        self.player_py = 5 * TILE
        self.moving = False
        self.move_target = (self.player_px, self.player_py)
        self.state = "overworld"
        self.start_dialog(
            [
                "Your party fainted...",
                "You hurried back to the heal point.",
                "Everyone was healed. Save from the menu or the red pad.",
            ],
            base_state="overworld",
            return_state="overworld",
        )

    # ---------------------------------------------------------------------
    # Drawing
    # ---------------------------------------------------------------------

    def draw(self) -> None:
        self.canvas.fill(BLACK)
        if self.state == "dialog":
            self.draw_base_state(self.dialog_base_state)
            self.textbox.draw(self.canvas)
        else:
            self.draw_base_state(self.state)

    def draw_base_state(self, state: str) -> None:
        if state == "title":
            self.draw_title()
        elif state in {"overworld", "pause", "party", "bag", "trainer", "options"}:
            self.draw_overworld()
            if state == "pause":
                self.draw_pause_menu()
            elif state == "party":
                self.draw_party_menu(overworld=True)
            elif state == "bag":
                self.draw_bag_menu(overworld=True)
            elif state == "trainer":
                self.draw_trainer_card()
            elif state == "options":
                self.draw_options_menu()
        elif state in {"battle", "battle_menu", "fight_menu", "battle_bag", "battle_party"}:
            self.draw_battle()
            if state == "battle_menu":
                self.draw_battle_commands()
            elif state == "fight_menu":
                self.draw_fight_menu()
            elif state == "battle_bag":
                self.draw_battle_bag_menu()
            elif state == "battle_party":
                self.draw_party_menu(overworld=False)
        else:
            self.draw_overworld()

    def draw_title(self) -> None:
        # Animated handheld-style title field.
        self.canvas.fill((208, 232, 248))
        t = pygame.time.get_ticks() / 1000
        for y in range(0, LOGICAL_H, 8):
            wobble = int(math.sin(t * 2 + y * 0.15) * 2)
            pygame.draw.rect(self.canvas, (184, 216, 240), (0, y + wobble, LOGICAL_W, 4))
        draw_text(self.canvas, self.big_font, "CHATGPTRED4K", 50, 22, FRAME_DARK)
        draw_text(self.canvas, self.font, "VERSION 1.0", 93, 43, INK)
        draw_text(self.canvas, self.small_font, "single file / pygame / 60 fps / json saves", 49, 58, SHADOW)
        draw_text(self.canvas, self.small_font, "Gameboy-style speed: 1 px/frame", 58, 70, SHADOW)
        menu_h = 18 + len(self.title_items) * 13
        menu_rect = pygame.Rect(72, 84, 104, menu_h)
        draw_window(self.canvas, menu_rect)
        for i, item in enumerate(self.title_items):
            y = menu_rect.y + 8 + i * 13
            draw_text(self.canvas, self.font, item, menu_rect.x + 22, y)
            if i == self.title_index:
                draw_text(self.canvas, self.font, "▶", menu_rect.x + 8, y)

    def draw_overworld(self) -> None:
        # Tiles.
        for ty, row in enumerate(self.map_rows):
            for tx, tile in enumerate(row):
                rect = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
                if tile == "T":
                    pygame.draw.rect(self.canvas, TREE_DARK, rect)
                    pygame.draw.rect(self.canvas, TREE, (rect.x + 2, rect.y + 2, 12, 12))
                    pygame.draw.rect(self.canvas, TREE_DARK, (rect.x + 6, rect.y + 10, 4, 5))
                elif tile == "G":
                    pygame.draw.rect(self.canvas, GRASS, rect)
                    for gx in (3, 9):
                        pygame.draw.line(self.canvas, GRASS_DARK, (rect.x + gx, rect.y + 13), (rect.x + gx + 2, rect.y + 8))
                elif tile == "H":
                    pygame.draw.rect(self.canvas, PATH, rect)
                    pygame.draw.rect(self.canvas, HEAL_RED, (rect.x + 2, rect.y + 2, 12, 12))
                    pygame.draw.rect(self.canvas, HEAL_PINK, (rect.x + 5, rect.y + 3, 6, 10))
                    pygame.draw.rect(self.canvas, HEAL_PINK, (rect.x + 3, rect.y + 5, 10, 6))
                else:
                    pygame.draw.rect(self.canvas, PATH, rect)
                    pygame.draw.rect(self.canvas, PATH_DARK, (rect.x, rect.y + 14, TILE, 2))

        # Professor NPC.
        if not self.prof_defeated:
            px, py = self.prof_pos[0] * TILE, self.prof_pos[1] * TILE
            self.draw_professor(px, py)
            draw_text(self.canvas, self.small_font, "PROF", px - 1, py - 9, INK)

        # Player.
        self.draw_player(self.player_px, self.player_py)

        # HUD hint.
        hint_rect = pygame.Rect(2, 2, 92, 16)
        pygame.draw.rect(self.canvas, (248, 248, 248), hint_rect)
        pygame.draw.rect(self.canvas, FRAME, hint_rect, 1)
        draw_text(self.canvas, self.small_font, "Z:talk  M:menu", 8, 6, INK)

    def draw_player(self, px: int, py: int) -> None:
        bob = 0
        if self.moving:
            bob = int(math.sin(pygame.time.get_ticks() / 80) * 1)
        x = px + 4
        y = py + 2 + bob
        pygame.draw.rect(self.canvas, PLAYER_HAT, (x + 1, y, 8, 3))
        pygame.draw.rect(self.canvas, (248, 200, 168), (x + 2, y + 3, 7, 5))
        pygame.draw.rect(self.canvas, PLAYER_BLUE, (x + 1, y + 8, 9, 7))
        pygame.draw.rect(self.canvas, BLACK, (x + 2, y + 14, 3, 2))
        pygame.draw.rect(self.canvas, BLACK, (x + 7, y + 14, 3, 2))

    def draw_professor(self, px: int, py: int) -> None:
        x = px + 4
        y = py + 1
        pygame.draw.rect(self.canvas, PROF_GRAY, (x + 2, y, 7, 4))
        pygame.draw.rect(self.canvas, (240, 200, 168), (x + 2, y + 4, 7, 5))
        pygame.draw.rect(self.canvas, PROF_COAT, (x, y + 9, 11, 7))
        pygame.draw.rect(self.canvas, FRAME_DARK, (x + 4, y + 9, 3, 7))

    def draw_pause_menu(self) -> None:
        rect = pygame.Rect(LOGICAL_W - 82, 8, 74, 98)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, "MENU", rect.x + 22, rect.y + 6, FRAME_DARK)
        for i, item in enumerate(self.pause_items):
            y = rect.y + 20 + i * 12
            draw_text(self.canvas, self.font, item, rect.x + 17, y)
            if i == self.pause_index:
                draw_text(self.canvas, self.font, "▶", rect.x + 6, y)

    def draw_party_menu(self, overworld: bool) -> None:
        if overworld:
            rect = pygame.Rect(10, 14, 150, 124)
        else:
            rect = pygame.Rect(12, 16, 156, 126)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, "PARTY", rect.x + 8, rect.y + 6, FRAME_DARK)
        cursor_idx = self.party_index if overworld else self.battle_party_index
        for i, mon in enumerate(self.player_party):
            y = rect.y + 23 + i * 30
            if i == cursor_idx:
                pygame.draw.rect(self.canvas, WINDOW_2, (rect.x + 5, y - 3, rect.width - 10, 25))
            status = "FNT" if mon.fainted else f"{mon.hp}/{mon.max_hp}"
            draw_text(self.canvas, self.font, f"{mon.name}  Lv{mon.level}", rect.x + 18, y)
            draw_hp_bar(self.canvas, rect.x + 18, y + 13, 58, mon.hp, mon.max_hp)
            draw_text(self.canvas, self.small_font, status, rect.x + 82, y + 10)
            if i == cursor_idx:
                draw_text(self.canvas, self.font, "▶", rect.x + 8, y)
        draw_text(self.canvas, self.small_font, "X:back", rect.x + 8, rect.bottom - 14, SHADOW)

    def draw_bag_menu(self, overworld: bool) -> None:
        rect = pygame.Rect(18, 18, 136, 112) if overworld else pygame.Rect(10, 88, 118, 62)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, "BAG", rect.x + 8, rect.y + 6, FRAME_DARK)
        items = self.bag_items() if overworld else self.battle_bag_items()
        cursor = self.bag_index if overworld else self.battle_bag_index
        for i, item in enumerate(items):
            y = rect.y + 22 + i * 13
            draw_text(self.canvas, self.font, item, rect.x + 20, y)
            if i == cursor:
                draw_text(self.canvas, self.font, "▶", rect.x + 8, y)
        if not overworld:
            draw_text(self.canvas, self.small_font, f"POTION x{self.inventory.get('POTION', 0)}", rect.x + 60, rect.y + 23, SHADOW)

    def draw_trainer_card(self) -> None:
        rect = pygame.Rect(24, 20, 188, 110)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, "TRAINER CARD", rect.x + 56, rect.y + 7, FRAME_DARK)
        draw_text(self.canvas, self.font, "NAME: PLAYER", rect.x + 12, rect.y + 28)
        draw_text(self.canvas, self.font, "ID: 00001", rect.x + 12, rect.y + 42)
        draw_text(self.canvas, self.font, f"PARTY: {len(self.player_party)}", rect.x + 12, rect.y + 56)
        draw_text(self.canvas, self.font, "BADGES: prototype", rect.x + 12, rect.y + 70)
        draw_text(self.canvas, self.small_font, f"SAVE FILE: {'YES' if self.save_exists() else 'NO'}", rect.x + 12, rect.y + 90, SHADOW)
        draw_text(self.canvas, self.small_font, "Z/X:back", rect.right - 50, rect.bottom - 14, SHADOW)

    def draw_options_menu(self) -> None:
        rect = pygame.Rect(36, 24, 160, 94)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, "OPTIONS", rect.x + 57, rect.y + 8, FRAME_DARK)
        options = [
            f"TEXT SPEED: {self.text_speed_label}",
            f"BATTLE STYLE: {self.battle_style_label}",
            "BACK",
        ]
        for i, item in enumerate(options):
            y = rect.y + 28 + i * 18
            draw_text(self.canvas, self.font, item, rect.x + 23, y)
            if i == self.option_index:
                draw_text(self.canvas, self.font, "▶", rect.x + 10, y)

    # ---------------------------------------------------------------------
    # Battle drawing
    # ---------------------------------------------------------------------

    def draw_battle(self) -> None:
        self.canvas.fill((216, 232, 240))
        draw_text(self.canvas, self.small_font, "PROFESSOR BOSS THEME", 132, 4, FRAME_DARK)
        pygame.draw.rect(self.canvas, (184, 216, 200), (0, 72, LOGICAL_W, 38))
        pygame.draw.ellipse(self.canvas, (152, 184, 152), (142, 55, 76, 16))
        pygame.draw.ellipse(self.canvas, (152, 184, 152), (24, 113, 84, 17))

        if self.enemy_party:
            self.draw_enemy_monster(170, 43)
            self.draw_enemy_status()
        if self.player_party:
            self.draw_player_monster(58, 100)
            self.draw_player_status()

        if self.battle_flash_timer > 0 and self.battle_flash_timer % 4 < 2:
            pygame.draw.rect(self.canvas, (255, 255, 255), (0, 0, LOGICAL_W, LOGICAL_H), 0)

    def draw_enemy_monster(self, x: int, y: int) -> None:
        # Placeholder monster sprite made from primitives.
        pygame.draw.ellipse(self.canvas, ENEMY_GREEN, (x - 20, y - 11, 41, 28))
        pygame.draw.circle(self.canvas, ENEMY_DARK, (x - 8, y - 2), 2)
        pygame.draw.circle(self.canvas, ENEMY_DARK, (x + 9, y - 2), 2)
        pygame.draw.polygon(self.canvas, ENEMY_GREEN, [(x - 10, y - 10), (x - 3, y - 22), (x + 2, y - 10)])
        pygame.draw.polygon(self.canvas, ENEMY_GREEN, [(x + 7, y - 9), (x + 17, y - 19), (x + 15, y - 6)])
        pygame.draw.arc(self.canvas, ENEMY_DARK, (x - 8, y + 2, 18, 8), 0, math.pi, 1)

    def draw_player_monster(self, x: int, y: int) -> None:
        pygame.draw.ellipse(self.canvas, ALLY_BLUE, (x - 22, y - 15, 46, 32))
        pygame.draw.circle(self.canvas, ALLY_DARK, (x - 8, y - 4), 2)
        pygame.draw.circle(self.canvas, ALLY_DARK, (x + 9, y - 4), 2)
        pygame.draw.rect(self.canvas, ALLY_BLUE, (x - 13, y - 25, 10, 15))
        pygame.draw.rect(self.canvas, ALLY_BLUE, (x + 4, y - 25, 10, 15))
        pygame.draw.arc(self.canvas, ALLY_DARK, (x - 9, y + 2, 20, 9), 0, math.pi, 1)

    def draw_enemy_status(self) -> None:
        mon = self.active_enemy
        rect = pygame.Rect(8, 10, 104, 34)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, f"{mon.name} Lv{mon.level}", rect.x + 6, rect.y + 5)
        draw_text(self.canvas, self.small_font, "HP", rect.x + 8, rect.y + 20, SHADOW)
        draw_hp_bar(self.canvas, rect.x + 25, rect.y + 21, 66, mon.hp, mon.max_hp)

    def draw_player_status(self) -> None:
        mon = self.active_player
        rect = pygame.Rect(122, 86, 108, 42)
        draw_window(self.canvas, rect)
        draw_text(self.canvas, self.font, f"{mon.name} Lv{mon.level}", rect.x + 6, rect.y + 5)
        draw_text(self.canvas, self.small_font, "HP", rect.x + 8, rect.y + 19, SHADOW)
        draw_hp_bar(self.canvas, rect.x + 25, rect.y + 20, 66, mon.hp, mon.max_hp)
        draw_text(self.canvas, self.small_font, f"{mon.hp}/{mon.max_hp}", rect.x + 54, rect.y + 29)

    def draw_battle_commands(self) -> None:
        draw_window(self.canvas, pygame.Rect(6, 124, 232, 34))
        draw_text(self.canvas, self.font, f"What will {self.active_player.name} do?", 14, 133)
        cmd_rect = pygame.Rect(132, 124, 106, 34)
        draw_window(self.canvas, cmd_rect)
        commands = ["FIGHT", "BAG", "PARTY", "RUN"]
        positions = [(144, 131), (188, 131), (144, 145), (188, 145)]
        for i, (cmd, pos) in enumerate(zip(commands, positions)):
            draw_text(self.canvas, self.font, cmd, pos[0] + 8, pos[1])
            if i == self.battle_menu_index:
                draw_text(self.canvas, self.font, "▶", pos[0], pos[1])

    def draw_fight_menu(self) -> None:
        draw_window(self.canvas, pygame.Rect(6, 110, 232, 48))
        moves = self.active_player.moves
        positions = [(16, 119), (112, 119), (16, 137), (112, 137)]
        for i, (move, pos) in enumerate(zip(moves, positions)):
            draw_text(self.canvas, self.font, move.name, pos[0] + 10, pos[1])
            if i == self.move_index:
                draw_text(self.canvas, self.font, "▶", pos[0], pos[1])
        chosen = moves[self.move_index]
        draw_text(self.canvas, self.small_font, f"PP {chosen.pp}/{chosen.max_pp}", 188, 145, SHADOW)

    def draw_battle_bag_menu(self) -> None:
        self.draw_bag_menu(overworld=False)
        draw_window(self.canvas, pygame.Rect(132, 124, 106, 34))
        draw_text(self.canvas, self.font, "Use item?", 144, 133)
        draw_text(self.canvas, self.small_font, "X:back", 144, 146, SHADOW)


# -----------------------------------------------------------------------------
# Entrypoint / smoke test
# -----------------------------------------------------------------------------


def run_self_test() -> None:
    game = Game()
    test_save = os.environ.get("CHATGPTRED4K_TEST_SAVE")
    game.save_path = Path(test_save) if test_save else Path.cwd() / SAVE_FILE_NAME

    for state in ("title", "overworld", "pause", "party", "bag", "trainer", "options"):
        game.state = state
        game.draw()

    game.enemy_party = game.make_enemy_party()
    game.player_active_idx = 0
    game.enemy_active_idx = 0
    for state in ("battle", "battle_menu", "fight_menu", "battle_bag", "battle_party"):
        game.state = state
        game.draw()

    assert FPS == 60, "FPS must stay locked to 60"
    assert PLAYER_SPEED == 1, "Gameboy-style movement must stay 1 px/frame"
    assert game.move_grid_cursor(1, 1, False) == 0, "battle grid should not wrap diagonally"
    assert game.move_grid_cursor(3, 1, False) == 2, "fight grid should not wrap diagonally"
    ok, message = game.save_game()
    assert ok, message
    ok, message = game.load_game()
    assert ok, message
    print(f"{GAME_TITLE} self-test passed: 60 FPS, 1 px/frame movement, menus, save/load, battle draw.")
    pygame.quit()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_test()
    else:
        Game().run()
