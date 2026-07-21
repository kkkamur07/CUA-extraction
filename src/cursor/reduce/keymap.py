"""Key-label mapping for OpenCUA action reduction.

Maps the keyboard-overlay layout labels (tootalltoby.json) onto the pyautogui
key space used by the AgentNet action format (OpenCUA, arXiv:2508.09123):
printable keys contribute characters to ``write(text)`` actions, special keys
become ``press(key)``, and modifier keys qualify combinations as ``hotkey``.
"""

from __future__ import annotations

# label -> (base_char, shifted_char) for keys that produce text (US layout)
PRINTABLE: dict[str, tuple[str, str]] = {
    **{chr(c): (chr(c).lower(), chr(c)) for c in range(ord("A"), ord("Z") + 1)},
    "1": ("1", "!"), "2": ("2", "@"), "3": ("3", "#"), "4": ("4", "$"),
    "5": ("5", "%"), "6": ("6", "^"), "7": ("7", "&"), "8": ("8", "*"),
    "9": ("9", "("), "0": ("0", ")"),
    "`": ("`", "~"), "-": ("-", "_"), "=": ("=", "+"),
    "[": ("[", "{"), "]": ("]", "}"), "\\": ("\\", "|"),
    ";": (";", ":"), "'": ("'", '"'),
    ",": (",", "<"), ".": (".", ">"), "/": ("/", "?"),
    "SPACE": (" ", " "),
    # numpad producing characters (NumLock assumed on; layout has no nav legend)
    **{f"NUM{d}": (str(d), str(d)) for d in range(10)},
    "NUM.": (".", "."), "NUM/": ("/", "/"), "NUM*": ("*", "*"),
    "NUM-": ("-", "-"), "NUM+": ("+", "+"),
}

# label -> pyautogui key name for press()/hotkey()
SPECIAL: dict[str, str] = {
    "ENTER": "enter", "NUMENTER": "enter", "TAB": "tab",
    "BACKSPACE": "backspace", "DELETE": "delete", "ESC": "esc",
    "HOME": "home", "END": "end", "PGUP": "pageup", "PGDN": "pagedown",
    "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right",
    "CAPSLOCK": "capslock", "NUMLOCK": "numlock",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
}

# modifier label -> pyautogui modifier name
MODIFIERS: dict[str, str] = {
    "LSHIFT": "shift", "RSHIFT": "shift",
    "LCTRL": "ctrl", "RCTRL": "ctrl",
    "LALT": "alt", "RALT": "alt",
    "WIN": "win",
}

# canonical ordering inside hotkey() calls, e.g. hotkey('ctrl', 'shift', 's')
MODIFIER_ORDER = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}


def is_modifier(label: str) -> bool:
    return label in MODIFIERS


def is_printable(label: str) -> bool:
    return label in PRINTABLE


def is_special(label: str) -> bool:
    return label in SPECIAL


def char_for(label: str, *, shifted: bool, capslock: bool = False) -> str:
    """Character produced by a printable key under shift/capslock state."""
    base, shift_char = PRINTABLE[label]
    if base.isalpha():
        return shift_char if (shifted ^ capslock) else base
    return shift_char if shifted else base


def hotkey_key_name(label: str) -> str:
    """Key name as it appears inside a hotkey combination."""
    if label in SPECIAL:
        return SPECIAL[label]
    if label in PRINTABLE:
        return PRINTABLE[label][0]
    return label.lower()
