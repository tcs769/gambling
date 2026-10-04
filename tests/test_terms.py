"""Title -> variants + threshold parsing, and config loading."""

import pytest

from mentionbot.config import ConfigError, Credentials, Settings
from mentionbot.terms import parse_threshold, parse_variants, term_market_from_api


# -- thresholds -------------------------------------------------------------
@pytest.mark.parametrize(
    "text, body, k",
    [
        ("Tariff", "Tariff", 1),
        ("Tariff (3+ times)", "Tariff", 3),
        ("Tariff (3 times)", "Tariff", 3),
        ("Tariff (2 time)", "Tariff", 2),
        ("Tariff (x5)", "Tariff", 5),
        ("Witch hunt 3+ times", "Witch hunt", 3),
        ("Tariff (1+ times)", "Tariff", 1),
    ],
)
def test_threshold_parsing(text, body, k):
    assert parse_threshold(text) == (body, k)


def test_threshold_defaults_to_one():
    assert parse_threshold("Inflation")[1] == 1


def test_threshold_never_below_one():
    assert parse_threshold("Tariff (0 times)")[1] == 1


# -- variants ---------------------------------------------------------------
def test_variants_split_on_slash_with_spaces():
    assert parse_variants("Tariff / Tariffs") == ["Tariff", "Tariffs"]


def test_slash_without_spaces_is_not_a_separator():
    """"and/or" is one term, not two."""
    assert parse_variants("and/or") == ["and/or"]


def test_variants_are_deduplicated_case_insensitively():
    assert parse_variants("Tariff / tariff / TARIFF") == ["Tariff"]


def test_variant_quotes_are_stripped():
    assert parse_variants('"Fake news" / “fake media”') == ["Fake news", "fake media"]


def test_empty_variants_are_dropped():
    assert parse_variants("Tariff /  / Trade") == ["Tariff", "Trade"]


# -- full market ------------------------------------------------------------
def test_market_from_api_uses_yes_sub_title():
    m = term_market_from_api({
        "ticker": "KXT-A", "title": "Will the speaker say Tariff?",
        "yes_sub_title": "Tariff / Tariffs (3+ times)",
        "rules_primary": "Counts if said.", "last_price": 37,
    })
    assert m.ticker == "KXT-A"
    assert m.variants == ["Tariff", "Tariffs"]
    assert m.threshold == 3
    assert m.opening_price == 37
    assert m.label == "Tariff"


def test_falls_back_to_title_when_no_subtitle():
    m = term_market_from_api({"ticker": "T", "title": "Inflation (2+ times)"})
    assert m.variants == ["Inflation"] and m.threshold == 2


def test_leading_say_scaffolding_is_stripped():
    m = term_market_from_api({"ticker": "T", "yes_sub_title": "Will Trump say: Tariff?"})
    assert m.variants == ["Tariff"]


def test_opening_price_falls_back_to_the_mid():
    m = term_market_from_api({"ticker": "T", "yes_sub_title": "Tariff",
                              "yes_bid": 40, "yes_ask": 46})
    assert m.opening_price == 43


def test_market_without_variants_is_not_tradable():
    m = term_market_from_api({"ticker": "T", "yes_sub_title": ""})
    assert not m.tradable


def test_flagged_market_is_not_tradable():
    m = term_market_from_api({"ticker": "T", "yes_sub_title": "Tariff"})
    assert m.tradable
    m.flagged_reason = "rules differ"
    assert not m.tradable


# -- settings ---------------------------------------------------------------
def test_shipped_config_loads():
    s = Settings.load("config.yaml")
    assert s.entry_gap == 15 and s.exit_gap == 5
    assert s.max_cents_per_event == 2500 and s.max_loss_cents == 2500


def test_unknown_setting_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("entry_gap: 15\nnot_a_setting: 1\n")
    with pytest.raises(ConfigError, match="not_a_setting"):
        Settings.load(p)


def test_moving_model_alias_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text('jev_model: "jev-latest"\n')
    with pytest.raises(ConfigError, match="pinned"):
        Settings.load(p)


def test_pinned_model_is_accepted(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text('jev_model: "jev-1.13.0"\n')
    assert Settings.load(p).jev_model == "jev-1.13.0"


@pytest.mark.parametrize(
    "body",
    [
        "entry_gap: 0",
        "contracts_per_entry: 0",
        "contracts_per_entry: 9\nmax_contracts_per_market: 5",
        "min_word_confidence: 1.5",
        "max_price_after_mention: 100",
        "max_dollars_per_event: 0",
        "max_loss_per_event: -1",
    ],
)
def test_invalid_settings_are_rejected(tmp_path, body):
    p = tmp_path / "c.yaml"
    p.write_text(body + "\n")
    with pytest.raises(ConfigError):
        Settings.load(p)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        Settings.load(tmp_path / "nope.yaml")


# -- credentials ------------------------------------------------------------
def test_missing_credentials_are_reported(monkeypatch):
    for var in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH",
                "ASSEMBLYAI_API_KEY", "TYPESAFE_API_KEY", "AI_GATEWAY_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError, match="KALSHI_API_KEY_ID"):
        Credentials.from_env()


def test_gateway_key_satisfies_the_jev_credential(monkeypatch, tmp_path):
    pem = tmp_path / "k.pem"
    pem.write_text("x")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(pem))
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "a")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "g")
    assert Credentials.from_env().typesafe_api_key == "g"


def test_missing_key_file_is_reported(monkeypatch, tmp_path):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(tmp_path / "absent.pem"))
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "a")
    monkeypatch.setenv("TYPESAFE_API_KEY", "t")
    with pytest.raises(ConfigError, match="does not exist"):
        Credentials.from_env()


def test_credentials_never_render_their_values(monkeypatch, tmp_path):
    pem = tmp_path / "k.pem"
    pem.write_text("x")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "super-secret-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(pem))
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "super-secret-assembly")
    monkeypatch.setenv("TYPESAFE_API_KEY", "super-secret-typesafe")
    rendered = repr(Credentials.from_env())
    assert "super-secret" not in rendered
