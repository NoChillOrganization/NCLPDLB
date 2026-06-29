from src.platform.seed import parse_species_aliases

SAMPLE = """
export const Aliases = {
\trandbats: "[Gen 9] Random Battle",
\turshifurs: "Urshifu-Rapid-Strike",
\tnidoranfemale: "Nidoran-F",
};
"""


def test_parse_species_aliases_skips_formats():
    pairs = parse_species_aliases(SAMPLE)
    assert ("urshifurs", "Urshifu-Rapid-Strike") in pairs
    assert ("nidoranfemale", "Nidoran-F") in pairs
    assert not any(k == "randbats" for k, _ in pairs)
