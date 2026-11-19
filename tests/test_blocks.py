import copy

import pytest

from src.art import blocks, prompt_builder
from src.art.test5 import CAST, LOCATIONS, PANELS, build_items
from src.common.config import phrases


def frozen():
    return blocks.freeze(CAST, LOCATIONS)


def test_character_block_fixed_order_and_name_first():
    b = blocks.character_block(CAST[0])
    assert b.startswith("Devan Thorai, a 32 year old man, wiry build, long narrow face, short wavy black hair, ")
    assert "dark brown eyes, deep brown skin, wearing a faded mustard-yellow kurta" in b
    assert blocks.character_block(copy.deepcopy(CAST[0])) == b  # byte-identical rebuild


def test_missing_field_rejected():
    bad = dict(CAST[0], eye_colour="")
    with pytest.raises(ValueError):
        blocks.character_block(bad)


def test_hash_check_refuses_modified_block():
    f = frozen()
    f["characters"]["Devan Thorai"]["block"] += " with a hat"
    with pytest.raises(ValueError):
        prompt_builder.build(PANELS[0], f)


def test_every_prompt_ends_with_style_phrase_and_contains_blocks_verbatim():
    f = frozen()
    style = phrases()["STYLE_PHRASE"]
    for it in build_items(f):
        assert it["prompt"].endswith(style)
    p = prompt_builder.build(PANELS[2], f)
    left, right = f["characters"]["Devan Thorai"]["block"], f["characters"]["Neela Varsi"]["block"]
    assert p.startswith(left + ", " + right + ", ")
    assert f["locations"]["street"]["block"] in p


def test_appearance_words_in_action_rejected():
    assert prompt_builder.lint_action("close-up, she smiles, her silver hair glowing")
    assert not prompt_builder.lint_action("close-up, worried expression, pressing both hands to her chest")
    with pytest.raises(ValueError):
        prompt_builder.build(dict(PANELS[0], action="close-up wearing a red scarf"), frozen())


def test_character_free_shot_has_no_blocks_and_max_two_characters():
    f = frozen()
    p = prompt_builder.build(PANELS[4], f)
    assert "Devan" not in p and "Neela" not in p and "no people" in p
    three = dict(PANELS[2], characters=PANELS[2]["characters"] + [{"name": "Devan Thorai", "side": "center"}])
    with pytest.raises(ValueError):
        prompt_builder.build(three, f)


def test_negative_phrase_verbatim():
    assert phrases()["NEGATIVE_PHRASE"].startswith("text, letters, words, speech bubble")


def test_seeds_are_deterministic():
    assert [i["seed"] for i in build_items(frozen())] == [i["seed"] for i in build_items(frozen())]
