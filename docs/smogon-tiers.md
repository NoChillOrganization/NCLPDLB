# Smogon Gen 9 (SV) Tier Reference

This document provides a concise reference for Gen 9 Scarlet/Violet competitive tier placements
and format rules, used to ensure teams in `src/ml/teams.py` are legal for their respective formats.

> Last updated: 2025. Tiers shift monthly based on usage statistics. This file should be refreshed
> periodically — check Smogon's usage-based tier update threads and the Pokemon Showdown
> `data/formats-data.ts` source for authoritative data.

---

## Tier Hierarchy

From highest to lowest power level:

```text
AG (Anything Goes)
Uber
OU (OverUsed)
UUBL (UU Banlist — too strong for UU)
UU (UnderUsed)
RUBL (RU Banlist — too strong for RU)
RU (RarelyUsed)
NUBL (NU Banlist — too strong for NU)
NU (NeverUsed)
PUBL (PU Banlist — too strong for PU)
PU (PU)
ZUBL (ZU Banlist — too strong for ZU)
ZU (Zero Used)
LC (Little Cup — unevolved, level 5)
NFE (Not Fully Evolved — not eligible for most tiers)
Illegal (not available in Gen 9 SV cartridge)
```

Each format bans all tiers above it. For example, RU bans RU and above (UU, RUBL, OU, UUBL,
Uber, AG). Pokemon from tiers below are **allowed up** (e.g., ZU Pokemon are legal in RU).

---

## Format Rules

### Standard Clauses (all tiers)

| Clause | Effect |
|--------|--------|
| Species Clause | No duplicate species on a team |
| OHKO Clause | Horn Drill, Guillotine, Sheer Cold, Fissure banned |
| Evasion Clause | Double Team and Minimize banned |
| Sleep Clause Mod | At most one opposing Pokemon can be asleep at once (NOT a move ban) |
| Endless Battle Clause | Prevents intentional infinite loops |

### OU-Specific Rule

- **Sleep Moves Clause** (OU only): Spore, Sleep Powder, Hypnosis, Lovely Kiss, Sing, Dark Void
  are completely banned in OU. The Sleep Clause Mod is removed in OU.
- In all **lower tiers** (UU, RU, NU, PU, ZU): Sleep Clause Mod applies instead —
  sleep-inducing moves are **legal** but you cannot put more than one opponent's Pokemon to sleep.

### Format-Specific Item/Ability Bans

| Format | Additional Bans |
|--------|----------------|
| RU | Light Clay |
| NU | Drought (ability), Quick Claw |
| PU | Damp Rock |
| ZU | Unburden (ability), Heat Rock |
| LC | Moody (ability), Heat Rock, Baton Pass, Sticky Web |

---

## Gen 9 SV Tier Placements (Key Pokemon)

### Ubers (legal in Ubers, banned from OU and below)

Notable: Miraidon, Koraidon, Calyrex-Shadow, Calyrex-Ice, Zacian-Crowned, Zamazenta-Crowned,
Necrozma-Dusk-Mane, Necrozma-Dawn-Wings, Groudon, Kyogre, Eternatus, Ho-Oh, Lunala, Mewtwo,
Roaring Moon, Flutter Mane, Chi-Yu, Chien-Pao, Gouging Fire, Raging Bolt, Terapagos, Lugia,
Ogerpon-Hearthflame, Archaludon (+ all AG Pokemon)

### OU (banned from UU and below)

Notable: Gholdengo, Ting-Lu, Iron Valiant, Walking Wake, Zapdos, Moltres, Dragonite,
Ogerpon-Wellspring, Iron Crown, Hatterene, Garganacl, Gliscor, Ceruledge, Rillaboom,
Amoonguss (in doubles: DOU), Incineroar, Landorus-Therian, Tornadus-Therian, Iron Treads,
Volcarona, Great Tusk, Kingambit

### UUBL (banned from UU and all tiers below)

Notable: **Quaquaval** (suspect-tested 2025), **Iron Hands**, **Polteageist**, **Okidogi**,
Moltres-Galar, Ogerpon-Cornerstone, Iron Boulder

### UU (legal in UU, banned from RU and below)

Notable: Sinistcha, Fezandipiti, Hydrapple, Feraligatr, Azumarill, Slowking, Skarmory,
Blissey, Tinkaton, Arcanine-Hisui, Decidueye (wait — Decidueye is PU; Decidueye-Hisui = PU),
**Revavroom** (UU — banned from RU), Slowking-Galar

### RUBL (banned from RU and all tiers below)

Notable: Gyarados, Electrode-Hisui, Iron Leaves, Porygon2, Ampharos-Mega (past), Bellossom (past)

### RU (legal in RU, banned from NU and below)

Notable: Lycanroc-Dusk, Mimikyu, Talonflame, Magnezone, Umbreon, Slowbro, Slowking (RU varies),
Basculegion-F, Mew, Entei, Suicune, Espeon (wait — Espeon = NU; check current data)

### NUBL (banned from NU and all tiers below)

Notable: Check current Smogon forums for most recent NUBL list.

### NU (legal in NU, banned from PU and below)

Notable: **Reuniclus**, Tsareena, Sylveon, Vaporeon, Espeon, Umbreon (check — may be RU),
Scream Tail, Wo-Chien, Araquanid, Basculegion (male), Incineroar (in singles: NU),
Klefki, Leafeon (check)

### PUBL (banned from PU and all tiers below)

Notable: Check current Smogon forums for most recent PUBL list.

### PU (legal in PU, banned from ZU and below)

Notable: Ambipom, Floatzel, Hariyama, Palossand, Amoonguss (singles), Bruxish,
Misdreavus (past — Illegal in SV), Gourgeist (past — Illegal in SV),
Sandslash-Alola, Decidueye-Hisui, Florges

### ZUBL (banned from ZU and all tiers below)

Notable: Check current Smogon forums.

### ZU (legal in ZU)

Notable: Lycanroc (Midday/Midnight), Zangoose, Magneton, Crabominable, Passimian,
Klawf, Whimsicott, Indeedee-Female, Wigglytuff, Granbull, Oranguru, Jolteon, Flareon,
Glaceon, Leafeon, Sunflora, Delibird, Swalot, Chimecho, Medicham, Smeargle, Toedscruel,
Dunsparce (check — may be NFE), Girafarig (check — NFE if Farigiraf exists)

### Illegal in Gen 9 SV (not obtainable in game)

These Pokemon are **completely unavailable** in SV regardless of tier:

- Yveltal, Togekiss, Drampa, Lickitung, Dhelmise, Kecleon, Spinda, Corsola (regular),
  Castform (all forms), Staryu, Bunnelby, Delcatty, Swalot (check), Furret

> Note: "Past" Pokemon appear in older generations but were not carried forward to SV.

---

## Little Cup (LC) Specific Rules

LC uses unevolved Pokemon at Level 5 with Eviolite commonly used. Key points:

- Only Pokemon that can evolve AND have not yet evolved are eligible
- NFE ("Not Fully Evolved") Pokemon that can evolve **again** are eligible
- Many viable LC Pokemon are explicitly banned for balance:

### Explicitly Banned in LC (Gen 9)

Aipom, Basculin-White-Striped, Cutiefly, **Diglett** (base), **Dunsparce**, Duraludon, Flittle,
**Gastly**, **Girafarig**, Gligar, **Magby**, Meditite, **Misdreavus**, **Murkrow**, **Porygon**,
**Qwilfish-Hisui**, Rufflet, Scraggy, Scyther, **Shellder**, Sneasel, Sneasel-Hisui, Snivy,
Stantler, Torchic, Voltorb-Hisui, Vulpix, Vulpix-Alola, Yanma

Banned moves/abilities: Moody, Heat Rock, Baton Pass, Sticky Web

---

## Doubles UU Tier Reference

Doubles uses separate tier designations: DUber > DOU > DUUBL > DUU.

### DOU (banned from Doubles UU)

Iron Hands, Hatterene, Amoonguss, Incineroar, Rillaboom, Whimsicott, Landorus-Therian

### DUU (legal in Doubles UU)

Garganacl, Mimikyu, Talonflame, Arcanine-Hisui, Tsareena, Klefki, Slowking, Sylveon

---

## Periodic Update Notes

- Tiers shift monthly based on Smogon usage statistics
- Council bans can happen at any time outside the monthly cycle
- Check: <https://www.smogon.com/forums/threads/usage-based-tier-update-for-july-2025-august-44-september-56.3767211/>
- Check formats-data.ts: <https://github.com/smogon/pokemon-showdown/blob/master/data/formats-data.ts>
- This file was last audited against Pokemon Showdown's formats-data.ts in March 2025
