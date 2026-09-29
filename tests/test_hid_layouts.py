"""Tests for the Pico firmware's keyboard layout tables (contrib/pico2w/hid_layouts.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "contrib" / "pico2w"))

import hid_layouts  # noqa: E402

PRINTABLE_ASCII = [chr(c) for c in range(0x20, 0x7F)]


@pytest.mark.parametrize("layout", sorted(hid_layouts.LAYOUTS))
def test_every_printable_character_is_typeable_one_way(layout):
    unshifted, shifted = hid_layouts.LAYOUTS[layout]
    assert len(unshifted) == len(shifted) == len(hid_layouts.KEYS)
    both = unshifted + shifted
    assert sorted(set(both)) == sorted(both), "a character is on two keys"

    keymap = hid_layouts.keymap(layout)
    for char in PRINTABLE_ASCII + ["\n", "\t"]:
        assert char in keymap, f"{char!r} can't be typed"


def test_us_layout():
    keymap = hid_layouts.keymap("us")
    assert keymap["a"] == (0x04, False)
    assert keymap["A"] == (0x04, True)
    assert keymap["!"] == (0x1E, True)
    assert keymap[" "] == (hid_layouts.SPACE, False)
    assert keymap["\n"] == (hid_layouts.ENTER, False)


def test_programmer_dvorak_layout():
    keymap = hid_layouts.keymap("dvp")
    # "hello" is typed with the QWERTY keys j d p p s
    assert [keymap[c] for c in "hello"] == [
        (0x0D, False),
        (0x07, False),
        (0x13, False),
        (0x13, False),
        (0x16, False),
    ]
    # Digits need Shift on the number row: 7 5 3 1 9 0 2 4 6 8
    assert keymap["1"] == (0x22, True)
    assert keymap["0"] == (0x24, True)
    assert keymap["&"] == (0x1E, False)
    assert keymap["$"] == (0x35, False)


def test_layout_names_are_case_insensitive_with_aliases():
    assert hid_layouts.keymap("DVP") == hid_layouts.keymap("programmer-dvorak")
    assert hid_layouts.keymap("qwerty") == hid_layouts.keymap("us")


def test_unknown_layout():
    with pytest.raises(ValueError, match="dvp"):
        hid_layouts.keymap("colemak")
