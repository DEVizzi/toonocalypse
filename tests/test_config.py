from src.common.config import categories, models, settings, style_guide


def test_series_name_single_value():
    assert settings()["series_name"] == "Toonocalypse"


def test_category_weights_sum_to_100_and_seeds_valid():
    cats = categories()
    assert sum(c["weight"] for c in cats["categories"].values()) == 100
    assert len(cats["seeds"]) == 10
    for s in cats["seeds"]:
        assert s["category"] in cats["categories"]
        assert 3 <= s["parts"] <= 5
        assert len(s["moral"].split()) <= settings()["story"]["moral_max_words"]


def test_style_guide_parsed():
    sg = style_guide()
    assert sg["positive"].startswith("Modern cinematic comic book art")
    for word in ["text", "watermark", "gore", "blood", "cowl"]:
        assert word in sg["negative"]


def test_no_banned_providers_in_config():
    blob = str(models()).lower()
    for banned in ["flux.1-dev", "pollinations", "huggingface.co/api", "cloudflare", "insightface", "instantid", "pulid"]:
        assert banned not in blob
