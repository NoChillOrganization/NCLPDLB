from src.platform.normalize.replay import _normalized_key


def test_normalized_key():
    assert _normalized_key("Urshifu-Rapid-Strike") == "urshifurapidstrike"
    assert _normalized_key("Iron Hands") == _normalized_key("iron hands")
