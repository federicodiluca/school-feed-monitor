import json

import pytest

from sfm.config_loader import load_config


def write(tmp_path, cfg):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


def test_defaults_and_site_normalization(tmp_path):
    cfg = load_config(write(tmp_path, {
        "telegram_token": "t",
        "catalog": False,
        "sites": [
            {"url": "https://a.example/feed/"},
            {"name": "B", "url": "https://b.example/novita", "type": "HTML", "default_follow": False},
        ],
    }))
    assert cfg["polling_minutes"] == 10 and cfg["data_retention_days"] == 7
    assert cfg["sites"][0] == {"url": "https://a.example/feed/", "name": "https://a.example/feed/", "type": "rss", "default_follow": True,
                               "kind": "other", "region": None, "province": None}
    assert cfg["sites"][1]["type"] == "html" and cfg["sites"][1]["default_follow"] is False


def test_sites_optional(tmp_path):
    assert load_config(write(tmp_path, {"telegram_token": "t", "catalog": False}))["sites"] == []


@pytest.mark.parametrize("cfg, match", [
    ({}, "telegram_token"),
    ({"telegram_token": "t", "sites": "no"}, "deve essere una lista"),
    ({"telegram_token": "t", "sites": [{"name": "x"}]}, "senza 'url'"),
    ({"telegram_token": "t", "sites": [{"url": "https://x", "type": "pdf"}]}, "type 'pdf'"),
])
def test_invalid_configs(tmp_path, cfg, match):
    with pytest.raises(ValueError, match=match):
        load_config(write(tmp_path, cfg))


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nope.json"))
