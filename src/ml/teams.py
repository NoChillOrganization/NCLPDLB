"""
Pre-built teams for each training format.

5 teams per format in Showdown export format.
Used by RotatingTeambuilder to cycle through diverse teams during RL training.

Formats covered:
  gen9ou           — standard OU, 5 teams (various archetypes)
  gen9nationaldex  — NatDex OU, 5 teams (older Pokemon available)
  gen9monotype     — Monotype, 5 teams (one per common type)
  gen9anythinggoes — Anything Goes, 5 teams (legendaries legal)
  gen9doublesou    — Doubles OU, 5 teams (doubles-oriented)
"""

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 OU
# ─────────────────────────────────────────────────────────────────────────────

GEN9OU = [

    # Team 1 — Bulky Offense (Tusk + Ghold core)
    """\
Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Swords Dance

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Ice Spinner
- Rapid Spin
- Stealth Rock

Dragapult @ Choice Scarf
Ability: Infiltrator
Tera Type: Dragon
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Dragon Pulse
- Shadow Ball
- Flamethrower
- U-turn

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower""",

    # Team 2 — Stall
    """\
Dondozo @ Leftovers
Ability: Unaware
Tera Type: Water
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Waterfall
- Rest
- Sleep Talk
- Wave Crash

Clodsire @ Black Sludge
Ability: Unaware
Tera Type: Poison
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Earthquake
- Toxic
- Recover
- Stealth Rock

Blissey @ Leftovers
Ability: Natural Cure
Tera Type: Normal
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Soft-Boiled
- Heal Bell
- Protect
- Thunder Wave

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 252 Def / 4 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Gliscor @ Toxic Orb
Ability: Poison Heal
Tera Type: Ground
EVs: 252 HP / 184 Def / 72 Spe
Impish Nature
- Earthquake
- U-turn
- Protect
- Knock Off

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Protect
- Flamethrower""",

    # Team 3 — Rain Offense
    """\
Pelipper @ Leftovers
Ability: Drizzle
Tera Type: Water
EVs: 248 HP / 8 SpA / 252 SpD
Calm Nature
- Surf
- Hurricane
- Roost
- U-turn

Barraskewda @ Life Orb
Ability: Swift Swim
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Liquidation
- Close Combat
- Flip Turn
- Psychic Fangs

Zapdos @ Heavy-Duty Boots
Ability: Static
Tera Type: Flying
EVs: 248 HP / 8 SpA / 252 Def
Bold Nature
- Thunderbolt
- Hurricane
- Roost
- Volt Switch

Iron Treads @ Heavy-Duty Boots
Ability: Quark Drive
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Iron Head
- Rapid Spin
- Stealth Rock

Swampert @ Leftovers
Ability: Torrent
Tera Type: Ground
EVs: 240 HP / 16 Atk / 252 Def
Relaxed Nature
- Waterfall
- Earthquake
- Stealth Rock
- Flip Turn

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Swords Dance""",

    # Team 4 — Trick Room
    """\
Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Ursaluna @ Flame Orb
Ability: Guts
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Facade
- Headlong Rush
- Crunch
- Swords Dance

Porygon2 @ Eviolite
Ability: Download
Tera Type: Normal
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Tri Attack
- Shadow Ball
- Thunderbolt
- Trick Room

Armarouge @ Choice Scarf
Ability: Flash Fire
Tera Type: Fire
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Armor Cannon
- Psychic
- Energy Ball
- Focus Blast

Mimikyu @ Life Orb
Ability: Disguise
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Play Rough
- Shadow Sneak
- Swords Dance
- Shadow Claw

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower""",

    # Team 5 — Sand
    """\
Tyranitar @ Smooth Rock
Ability: Sand Stream
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Crunch
- Stealth Rock
- Dragon Dance

Excadrill @ Life Orb
Ability: Sand Rush
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Earthquake
- Iron Head
- Rock Slide
- Rapid Spin

Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Ground
EVs: 252 HP / 164 Def / 92 Spe
Impish Nature
- Earthquake
- Stealth Rock
- Dragon Tail
- Fire Fang

Scizor @ Choice Band
Ability: Technician
Tera Type: Steel
EVs: 248 HP / 252 Atk / 8 SpD
Adamant Nature
- U-turn
- Bullet Punch
- Iron Head
- Knock Off

Rotom-Wash @ Leftovers
Ability: Levitate
Tera Type: Water
EVs: 248 HP / 252 SpA / 8 Spe
Modest Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Blissey @ Leftovers
Ability: Natural Cure
Tera Type: Normal
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Soft-Boiled
- Heal Bell
- Protect
- Thunder Wave""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 National Dex
# ─────────────────────────────────────────────────────────────────────────────

GEN9NATIONALDEX = [

    # Team 1 — Classic Balance
    """\
Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Ground
EVs: 252 HP / 240 Def / 16 Spe
Impish Nature
- Earthquake
- U-turn
- Stealth Rock
- Rock Slide

Rotom-Wash @ Leftovers
Ability: Levitate
Tera Type: Water
EVs: 248 HP / 252 SpA / 8 Spe
Modest Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower

Scizor @ Choice Band
Ability: Technician
Tera Type: Steel
EVs: 248 HP / 252 Atk / 8 SpD
Adamant Nature
- U-turn
- Bullet Punch
- Superpower
- Knock Off

Heatran @ Leftovers
Ability: Flash Fire
Tera Type: Steel
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Magma Storm
- Earth Power
- Stealth Rock
- Taunt

Latios @ Choice Specs
Ability: Levitate
Tera Type: Dragon
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Psyshock
- Thunderbolt
- Trick""",

    # Team 2 — Fairy Offense
    """\
Iron Valiant @ Choice Scarf
Ability: Quark Drive
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Dazzling Gleam
- Shadow Ball
- Trick

Gardevoir @ Choice Specs
Ability: Trace
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Psyshock
- Focus Blast
- Trick

Tyranitar @ Choice Band
Ability: Sand Stream
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Crunch
- Pursuit
- Earthquake

Iron Treads @ Heavy-Duty Boots
Ability: Quark Drive
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Iron Head
- Rapid Spin
- Stealth Rock

Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Ground
EVs: 252 HP / 164 Def / 92 Spe
Impish Nature
- Earthquake
- Stealth Rock
- Dragon Tail
- Fire Fang

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Ice Spinner
- Rapid Spin
- Stealth Rock""",

    # Team 3 — Hazard Stack
    """\
Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Ground
EVs: 252 HP / 164 Def / 92 Spe
Impish Nature
- Earthquake
- Stealth Rock
- Dragon Tail
- Fire Fang

Iron Treads @ Heavy-Duty Boots
Ability: Quark Drive
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Iron Head
- Rapid Spin
- Stealth Rock

Toxapex @ Black Sludge
Ability: Regenerator
Tera Type: Poison
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Surf
- Recover
- Toxic Spikes
- Haze

Zapdos @ Heavy-Duty Boots
Ability: Static
Tera Type: Flying
EVs: 248 HP / 8 SpA / 252 Def
Bold Nature
- Thunderbolt
- Hurricane
- Roost
- Volt Switch

Blissey @ Leftovers
Ability: Natural Cure
Tera Type: Normal
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Soft-Boiled
- Wish
- Protect
- Toxic

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick""",

    # Team 4 — Sun offense
    """\
Ninetales @ Heat Rock
Ability: Drought
Tera Type: Fire
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Fire Blast
- Solar Beam
- Hypnosis
- Nasty Plot

Venusaur @ Focus Sash
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Solar Beam
- Sludge Bomb
- Sleep Powder
- Earth Power

Heatran @ Choice Scarf
Ability: Flash Fire
Tera Type: Fire
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Magma Storm
- Earth Power
- Flash Cannon
- Ancient Power

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Swords Dance

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Ice Spinner
- Rapid Spin
- Stealth Rock""",

    # Team 5 — Volt-Turn
    """\
Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- U-turn
- Stone Edge
- Rock Slide

Rotom-Wash @ Leftovers
Ability: Levitate
Tera Type: Water
EVs: 248 HP / 252 SpA / 8 Spe
Modest Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Scizor @ Choice Band
Ability: Technician
Tera Type: Steel
EVs: 248 HP / 252 Atk / 8 SpD
Adamant Nature
- U-turn
- Bullet Punch
- Superpower
- Knock Off

Zapdos @ Heavy-Duty Boots
Ability: Static
Tera Type: Flying
EVs: 248 HP / 8 SpA / 252 Def
Bold Nature
- Thunderbolt
- Hurricane
- Roost
- Volt Switch

Tyranitar @ Choice Band
Ability: Sand Stream
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Crunch
- Earthquake
- Ice Punch

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Monotype (all 6 Pokemon share the listed type)
# ─────────────────────────────────────────────────────────────────────────────

GEN9MONOTYPE = [

    # Team 1 — Water
    """\
Toxapex @ Black Sludge
Ability: Regenerator
Tera Type: Water
EVs: 252 HP / 252 Def / 4 SpD
Bold Nature
- Surf
- Recover
- Toxic
- Haze

Dondozo @ Leftovers
Ability: Unaware
Tera Type: Water
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Waterfall
- Rest
- Sleep Talk
- Wave Crash

Rotom-Wash @ Leftovers
Ability: Levitate
Tera Type: Water
EVs: 248 HP / 252 SpA / 8 Spe
Modest Nature
- Volt Switch
- Hydro Pump
- Will-O-Wisp
- Pain Split

Barraskewda @ Choice Band
Ability: Swift Swim
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Liquidation
- Close Combat
- Flip Turn
- Psychic Fangs

Pelipper @ Leftovers
Ability: Drizzle
Tera Type: Water
EVs: 248 HP / 8 SpA / 252 SpD
Calm Nature
- Surf
- Hurricane
- Roost
- U-turn

Greninja @ Life Orb
Ability: Protean
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hydro Pump
- Dark Pulse
- Ice Beam
- U-turn""",

    # Team 2 — Steel
    """\
Scizor @ Choice Band
Ability: Technician
Tera Type: Steel
EVs: 248 HP / 252 Atk / 8 SpD
Adamant Nature
- U-turn
- Bullet Punch
- Iron Head
- Knock Off

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Steel
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Heatran @ Leftovers
Ability: Flash Fire
Tera Type: Steel
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Magma Storm
- Earth Power
- Stealth Rock
- Taunt

Iron Treads @ Choice Scarf
Ability: Quark Drive
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Iron Head
- Rapid Spin
- Ice Spinner

Magnezone @ Choice Scarf
Ability: Analytic
Tera Type: Steel
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Flash Cannon
- Volt Switch
- Body Press""",

    # Team 3 — Dragon
    """\
Dragapult @ Choice Scarf
Ability: Infiltrator
Tera Type: Dragon
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Dragon Pulse
- Shadow Ball
- Flamethrower
- U-turn

Roaring Moon @ Life Orb
Ability: Protosynthesis
Tera Type: Dragon
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Acrobatics
- Knock Off
- Dragon Dance
- Earthquake

Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Dragon
EVs: 252 HP / 164 Def / 92 Spe
Impish Nature
- Earthquake
- Stealth Rock
- Dragon Tail
- Fire Fang

Dragonite @ Heavy-Duty Boots
Ability: Multiscale
Tera Type: Dragon
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Dragon Dance
- Extreme Speed
- Earthquake
- Fire Punch

Hydreigon @ Choice Specs
Ability: Levitate
Tera Type: Dragon
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Draco Meteor
- Dark Pulse
- Flash Cannon
- U-turn

Noivern @ Choice Scarf
Ability: Infiltrator
Tera Type: Dragon
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hurricane
- Dragon Pulse
- U-turn
- Flamethrower""",

    # Team 4 — Fairy
    """\
Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower

Flutter Mane @ Choice Scarf
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Psyshock
- Dazzling Gleam

Gardevoir @ Choice Specs
Ability: Trace
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Psyshock
- Focus Blast
- Trick

Azumarill @ Choice Band
Ability: Huge Power
Tera Type: Water
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Aqua Jet
- Play Rough
- Knock Off
- Ice Punch

Sylveon @ Leftovers
Ability: Pixilate
Tera Type: Fairy
EVs: 252 HP / 252 SpA / 4 SpD
Modest Nature
- Hyper Voice
- Shadow Ball
- Calm Mind
- Protect

Mimikyu @ Life Orb
Ability: Disguise
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Play Rough
- Shadow Sneak
- Swords Dance
- Shadow Claw""",

    # Team 5 — Ground
    """\
Garchomp @ Rocky Helmet
Ability: Rough Skin
Tera Type: Ground
EVs: 252 HP / 164 Def / 92 Spe
Impish Nature
- Earthquake
- Stealth Rock
- Dragon Tail
- Fire Fang

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Ice Spinner
- Rapid Spin
- Knock Off

Gliscor @ Toxic Orb
Ability: Poison Heal
Tera Type: Ground
EVs: 252 HP / 184 Def / 72 Spe
Impish Nature
- Earthquake
- U-turn
- Protect
- Knock Off

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- U-turn
- Stone Edge
- Rock Slide

Clodsire @ Black Sludge
Ability: Unaware
Tera Type: Poison
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Earthquake
- Toxic
- Recover
- Stealth Rock

Iron Treads @ Life Orb
Ability: Quark Drive
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Iron Head
- Rapid Spin
- Ice Spinner""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Anything Goes
# ─────────────────────────────────────────────────────────────────────────────

GEN9ANYTHINGGOES = [

    # Team 1 — Restricted Offense
    """\
Zacian-Crowned @ Rusted Sword
Ability: Intrepid Sword
Tera Type: Fairy
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Behemoth Blade
- Play Rough
- Wild Charge
- Close Combat

Kyogre @ Choice Specs
Ability: Drizzle
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Water Spout
- Origin Pulse
- Ice Beam
- Thunder

Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Ground
EVs: 252 HP / 240 Def / 16 Spe
Impish Nature
- Earthquake
- U-turn
- Stealth Rock
- Rock Slide

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Swords Dance""",

    # Team 2 — Sun Legendaries
    """\
Groudon @ Earth Plate
Ability: Drought
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Precipice Blades
- Fire Punch
- Stealth Rock
- Rock Slide

Rayquaza @ Life Orb
Ability: Air Lock
Tera Type: Dragon
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Dragon Ascent
- Extreme Speed
- Earthquake
- Dragon Dance

Ho-Oh @ Life Orb
Ability: Regenerator
Tera Type: Fire
EVs: 252 Atk / 4 SpD / 252 Spe
Adamant Nature
- Sacred Fire
- Brave Bird
- Earthquake
- Recover

Flutter Mane @ Choice Specs
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Mystical Fire
- Dazzling Gleam

Necrozma-Dusk-Mane @ Life Orb
Ability: Prism Armor
Tera Type: Steel
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Sunsteel Strike
- Earthquake
- Dragon Dance
- Knock Off

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Ice Spinner
- Rapid Spin
- Stealth Rock""",

    # Team 3 — Rain Legendaries
    """\
Kyogre @ Choice Specs
Ability: Drizzle
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Water Spout
- Origin Pulse
- Ice Beam
- Thunder

Palkia @ Choice Specs
Ability: Pressure
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Spacial Rend
- Hydro Pump
- Fire Blast
- Thunder

Zamazenta-Crowned @ Rusted Shield
Ability: Dauntless Shield
Tera Type: Steel
EVs: 252 HP / 252 Def / 4 SpD
Impish Nature
- Body Press
- Iron Defense
- Crunch
- Protect

Eternatus @ Leftovers
Ability: Pressure
Tera Type: Poison
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Flamethrower
- Sludge Bomb
- Recover
- Dragon Pulse

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick""",

    # Team 4 — Trick Room Legendaries
    """\
Calyrex-Ice @ Weakness Policy
Ability: As One (Glastrier)
Tera Type: Ice
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Glacial Lance
- High Horsepower
- Protect
- Trick Room

Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Ursaluna @ Flame Orb
Ability: Guts
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Facade
- Headlong Rush
- Crunch
- Swords Dance

Necrozma @ Power Herb
Ability: Prism Armor
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Photon Geyser
- Flash Cannon
- Power Gem
- Trick Room

Zacian-Crowned @ Rusted Sword
Ability: Intrepid Sword
Tera Type: Fairy
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Behemoth Blade
- Play Rough
- Wild Charge
- Close Combat

Clefable @ Leftovers
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Moonblast
- Calm Mind
- Moonlight
- Flamethrower""",

    # Team 5 — Balanced Restricted
    """\
Lugia @ Leftovers
Ability: Multiscale
Tera Type: Psychic
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Aeroblast
- Whirlwind
- Recover
- Ice Beam

Zekrom @ Choice Band
Ability: Teravolt
Tera Type: Dragon
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Bolt Strike
- Dragon Claw
- Outrage
- Zen Headbutt

Miraidon @ Choice Specs
Ability: Hadron Engine
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Electro Drift
- Draco Meteor
- Dazzling Gleam
- Volt Switch

Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Ground
EVs: 252 HP / 240 Def / 16 Spe
Impish Nature
- Earthquake
- U-turn
- Stealth Rock
- Rock Slide

Corviknight @ Leftovers
Ability: Pressure
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Careful Nature
- Body Press
- Roost
- Defog
- U-turn

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Doubles OU
# ─────────────────────────────────────────────────────────────────────────────

GEN9DOUBLESOU = [

    # Team 1 — Urshifu + Rillaboom
    """\
Ogerpon-Wellspring @ Wellspring Mask
Ability: Water Absorb
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Ivy Cudgel
- Horn Leech
- Follow Me
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Iron Valiant @ Booster Energy
Ability: Quark Drive
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Dazzling Gleam
- Shadow Ball
- Protect

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect

Heatran @ Safety Goggles
Ability: Flash Fire
Tera Type: Steel
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Heat Wave
- Flash Cannon
- Earth Power
- Protect""",

    # Team 2 — Ogerpon + Kingambit
    """\
Ogerpon-Wellspring @ Wellspring Mask
Ability: Water Absorb
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Ivy Cudgel
- Horn Leech
- Follow Me
- Spiky Shield

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Iron Bundle @ Choice Scarf
Ability: Quark Drive
Tera Type: Ice
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hydro Pump
- Freeze-Dry
- U-turn
- Icy Wind

Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane""",

    # Team 3 — Trick Room
    """\
Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Ursaluna @ Flame Orb
Ability: Guts
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Facade
- Headlong Rush
- Crunch
- Protect

Porygon2 @ Eviolite
Ability: Download
Tera Type: Normal
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Tri Attack
- Shadow Ball
- Trick Room
- Protect

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Iron Hands @ Assault Vest
Ability: Quark Drive
Tera Type: Electric
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Wild Charge
- Close Combat
- Fake Out
- Drain Punch

Indeedee-F @ Psychic Seed
Ability: Psychic Surge
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Follow Me
- Trick Room
- Helping Hand""",

    # Team 4 — Tailwind
    """\
Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane

Sylveon @ Choice Specs
Ability: Pixilate
Tera Type: Fairy
EVs: 252 HP / 252 SpA / 4 Spe
Modest Nature
- Hyper Voice
- Psychic
- Shadow Ball
- Protect

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Protect

Garchomp @ Life Orb
Ability: Rough Skin
Tera Type: Dragon
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Dragon Claw
- Scale Shot
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick""",

    # Team 5 — Sun + Chlorophyll
    """\
Torkoal @ Heat Rock
Ability: Drought
Tera Type: Fire
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Heat Wave
- Earth Power
- Stealth Rock
- Protect

Venusaur @ Focus Sash
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Solar Beam
- Sludge Bomb
- Sleep Powder
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 VGC 2026 Reg I  (one restricted legendary allowed, level 50 flat rules)
# ─────────────────────────────────────────────────────────────────────────────

GEN9VGC2026REGI = [

    # Team 1 — Zacian restricted + Flutter Mane
    """\
Zacian-Crowned @ Rusted Sword
Ability: Intrepid Sword
Tera Type: Fairy
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Behemoth Blade
- Play Rough
- Wild Charge
- Protect

Flutter Mane @ Life Orb
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Protect
- Dazzling Gleam

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect""",

    # Team 2 — Kyogre restricted + Tailwind
    """\
Kyogre @ Choice Specs
Ability: Drizzle
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Water Spout
- Origin Pulse
- Ice Beam
- Protect

Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane

Urshifu-Rapid-Strike @ Choice Band
Ability: Unseen Fist
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Surging Strikes
- Close Combat
- U-turn
- Aqua Jet

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect""",

    # Team 3 — Calyrex-Ice restricted + Trick Room
    """\
Calyrex-Ice @ Weakness Policy
Ability: As One (Glastrier)
Tera Type: Ice
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Glacial Lance
- High Horsepower
- Close Combat
- Protect

Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Ursaluna @ Flame Orb
Ability: Guts
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Facade
- Headlong Rush
- Crunch
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Flutter Mane @ Life Orb
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Protect
- Dazzling Gleam""",

    # Team 4 — Groudon restricted + Sun
    """\
Groudon @ Earth Plate
Ability: Drought
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Precipice Blades
- Fire Punch
- Rock Slide
- Protect

Venusaur @ Focus Sash
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Solar Beam
- Sludge Bomb
- Sleep Powder
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Flutter Mane @ Life Orb
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Protect
- Dazzling Gleam

Urshifu-Rapid-Strike @ Choice Band
Ability: Unseen Fist
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Surging Strikes
- Close Combat
- U-turn
- Aqua Jet

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect""",

    # Team 5 — Calyrex-Shadow restricted + Tailwind Offense
    """\
Calyrex-Shadow @ Life Orb
Ability: As One (Spectrier)
Tera Type: Psychic
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Astral Barrage
- Psyshock
- Shadow Ball
- Protect

Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane

Urshifu-Rapid-Strike @ Choice Band
Ability: Unseen Fist
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Surging Strikes
- Close Combat
- U-turn
- Aqua Jet

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Flutter Mane @ Choice Specs
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Protect
- Dazzling Gleam""",

]


# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 VGC 2026 Reg F  (Flat Rules — no restricted legendaries allowed)
# ─────────────────────────────────────────────────────────────────────────────

GEN9VGC2026REGF = [

    # Team 1 — Tailwind offense
    """Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect""",

    # Team 2 — Trick Room
    """Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Ursaluna @ Flame Orb
Ability: Guts
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Facade
- Headlong Rush
- Crunch
- Protect

Porygon2 @ Eviolite
Ability: Download
Tera Type: Normal
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Tri Attack
- Shadow Ball
- Trick Room
- Protect

Iron Hands @ Assault Vest
Ability: Quark Drive
Tera Type: Electric
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Wild Charge
- Close Combat
- Fake Out
- Drain Punch

Indeedee-F @ Psychic Seed
Ability: Psychic Surge
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Follow Me
- Trick Room
- Helping Hand

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect""",

    # Team 3 — Rain offense
    """Pelipper @ Leftovers
Ability: Drizzle
Tera Type: Water
EVs: 248 HP / 8 SpA / 252 SpD
Calm Nature
- Surf
- Hurricane
- Protect
- U-turn

Urshifu-Rapid-Strike @ Choice Band
Ability: Unseen Fist
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Surging Strikes
- Close Combat
- U-turn
- Aqua Jet

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect""",

    # Team 4 — Sun + Chlorophyll
    """Torkoal @ Heat Rock
Ability: Drought
Tera Type: Fire
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Heat Wave
- Earth Power
- Stealth Rock
- Protect

Venusaur @ Focus Sash
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Solar Beam
- Sludge Bomb
- Sleep Powder
- Protect

Landorus-Therian @ Choice Scarf
Ability: Intimidate
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Earthquake
- Rock Slide
- U-turn
- Protect

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect

Gholdengo @ Choice Specs
Ability: Good as Gold
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Focus Blast
- Trick

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect""",

    # Team 5 — Balanced
    """Ogerpon-Wellspring @ Wellspring Mask
Ability: Water Absorb
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Ivy Cudgel
- Horn Leech
- Follow Me
- Protect

Kingambit @ Black Glasses
Ability: Supreme Overlord
Tera Type: Flying
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Kowtow Cleave
- Iron Head
- Sucker Punch
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- U-turn
- Wood Hammer
- Fake Out

Tornadus @ Focus Sash
Ability: Prankster
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Rain Dance
- Taunt
- Hurricane

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect""",

]


# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Ubers
# ─────────────────────────────────────────────────────────────────────────────

GEN9UBERS = [

    # Team 1 — Miraidon Hyper Offense
    """\
Miraidon @ Choice Specs
Ability: Hadron Engine
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Electro Drift
- Draco Meteor
- Overheat
- Volt Switch

Koraidon @ Choice Band
Ability: Orichalcum Pulse
Tera Type: Fire
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Collision Course
- Flare Blitz
- Drain Punch
- U-turn

Mewtwo @ Focus Sash
Ability: Pressure
Tera Type: Psychic
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Psystrike
- Aura Sphere
- Ice Beam
- Calm Mind

Gholdengo @ Choice Scarf
Ability: Good as Gold
Tera Type: Steel
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Make It Rain
- Shadow Ball
- Trick
- Nasty Plot

Ting-Lu @ Leftovers
Ability: Vessel of Ruin
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Earthquake
- Whirlwind
- Stealth Rock
- Ruination

Eternatus @ Choice Specs
Ability: Pressure
Tera Type: Poison
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Dynamax Cannon
- Shadow Ball
- Flamethrower
- Sludge Wave
""",

    # Team 2 — Calyrex-Shadow Balance
    """\
Lunala @ Choice Scarf
Ability: Shadow Shield
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moongeist Beam
- Psyshock
- Shadow Ball
- Trick

Eternatus @ Choice Specs
Ability: Pressure
Tera Type: Poison
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Dragon Pulse
- Sludge Bomb
- Flamethrower
- Shadow Ball

Necrozma-Dusk-Mane @ Leftovers
Ability: Prism Armor
Tera Type: Steel
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Sunsteel Strike
- Morning Sun
- Swords Dance
- Stealth Rock

Zacian-Crowned @ Rusted Sword
Ability: Intrepid Sword
Tera Type: Fairy
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Behemoth Blade
- Close Combat
- Wild Charge
- Sacred Sword

Ho-Oh @ Heavy-Duty Boots
Ability: Regenerator
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Sacred Fire
- Brave Bird
- Earthquake
- Recover

Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- U-turn
- Rock Slide
- Stealth Rock
""",

    # Team 3 — Trick Room Ubers
    """\
Calyrex-Ice @ Weakness Policy
Ability: As One (Glastrier)
Tera Type: Ice
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Glacial Lance
- High Horsepower
- Close Combat
- Swords Dance

Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Groudon @ Leftovers
Ability: Drought
Tera Type: Ground
EVs: 252 Atk / 4 Def / 252 HP
Brave Nature
IVs: 0 Spe
- Precipice Blades
- Fire Punch
- Stone Edge
- Rock Polish

Zamazenta-Crowned @ Rusted Shield
Ability: Dauntless Shield
Tera Type: Steel
EVs: 252 HP / 252 Def / 4 SpD
Relaxed Nature
IVs: 0 Spe
- Behemoth Bash
- Body Press
- Wide Guard
- Protect

Kyogre @ Choice Specs
Ability: Drizzle
Tera Type: Water
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Water Spout
- Origin Pulse
- Ice Beam
- Thunder

Necrozma-Dawn-Wings @ Leftovers
Ability: Prism Armor
Tera Type: Psychic
EVs: 252 HP / 4 Def / 252 SpA
Quiet Nature
IVs: 0 Spe
- Moongeist Beam
- Prismatic Laser
- Trick Room
- Stealth Rock
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 UU
# ─────────────────────────────────────────────────────────────────────────────

GEN9UU = [

    # Team 1 — Arcanine-Hisui Offense
    """\
Arcanine-Hisui @ Heavy-Duty Boots
Ability: Rock Head
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Flare Blitz
- Head Smash
- Close Combat
- Extreme Speed

Feraligatr @ Life Orb
Ability: Sheer Force
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Waterfall
- Ice Punch
- Crunch
- Dragon Dance

Reuniclus @ Life Orb
Ability: Magic Guard
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Shadow Ball
- Focus Blast
- Trick Room

Slowking @ Assault Vest
Ability: Regenerator
Tera Type: Water
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Surf
- Future Sight
- Flamethrower
- Ice Beam

Tinkaton @ Rocky Helmet
Ability: Mold Breaker
Tera Type: Fairy
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Gigaton Hammer
- Knock Off
- Stealth Rock
- Thunder Wave

Decidueye-Hisui @ Choice Band
Ability: Long Reach
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Triple Arrows
- Poltergeist
- Close Combat
- U-turn
""",

    # Team 2 — Slowbro Stall
    """\
Slowbro @ Heavy-Duty Boots
Ability: Regenerator
Tera Type: Water
EVs: 252 HP / 252 Def / 4 SpA
Bold Nature
- Surf
- Future Sight
- Slack Off
- Thunder Wave

Scream Tail @ Leftovers
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Wish
- Protect
- Dazzling Gleam
- Encore

Tinkaton @ Rocky Helmet
Ability: Mold Breaker
Tera Type: Fairy
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Gigaton Hammer
- Knock Off
- Stealth Rock
- Thunder Wave

Wo-Chien @ Leftovers
Ability: Tablets of Ruin
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Leech Seed
- Giga Drain
- Ruination
- Ingrain

Reuniclus @ Life Orb
Ability: Magic Guard
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Shadow Ball
- Focus Blast
- Trick Room

Sinistcha @ Leftovers
Ability: Hospitality
Tera Type: Grass
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Matcha Gotcha
- Shadow Ball
- Strength Sap
- Calm Mind
""",

    # Team 3 — Decidueye-Hisui Spikes Stack
    """\
Decidueye-Hisui @ Choice Band
Ability: Long Reach
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Triple Arrows
- Poltergeist
- Close Combat
- U-turn

Magnezone @ Choice Scarf
Ability: Magnet Pull
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Flash Cannon
- Volt Switch
- Thunder Wave

Sinistcha @ Leftovers
Ability: Hospitality
Tera Type: Grass
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Matcha Gotcha
- Shadow Ball
- Strength Sap
- Calm Mind

Arcanine-Hisui @ Heavy-Duty Boots
Ability: Rock Head
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Flare Blitz
- Head Smash
- Close Combat
- Extreme Speed

Azumarill @ Assault Vest
Ability: Huge Power
Tera Type: Water
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Liquidation
- Play Rough
- Aqua Jet
- Knock Off

Fezandipiti @ Heavy-Duty Boots
Ability: Toxic Chain
Tera Type: Poison
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Hyper Drill
- Roost
- Toxic
- Knock Off
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 RU
# ─────────────────────────────────────────────────────────────────────────────

GEN9RU = [

    # Team 1 — Lycanroc-Dusk Offense
    """\
Lycanroc-Dusk @ Choice Band
Ability: Tough Claws
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Close Combat
- Accelerock
- Fire Fang

Tsareena @ Heavy-Duty Boots
Ability: Queenly Majesty
Tera Type: Grass
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Power Whip
- Rapid Spin
- Triple Axel
- High Jump Kick

Passimian @ Choice Scarf
Ability: Receiver
Tera Type: Fighting
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Close Combat
- U-turn
- Knock Off
- Rock Slide

Basculegion @ Choice Band
Ability: Swift Swim
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Wave Crash
- Crunch
- Aqua Jet
- Shadow Ball

Bruxish @ Life Orb
Ability: Strong Jaw
Tera Type: Water
EVs: 252 Atk / 4 SpA / 252 Spe
Jolly Nature
- Psychic Fangs
- Crunch
- Aqua Jet
- Ice Fang

Klawf @ Sitrus Berry
Ability: Anger Shell
Tera Type: Rock
EVs: 4 HP / 252 Atk / 252 Spe
Jolly Nature
- Stone Edge
- Knock Off
- X-Scissor
- Stealth Rock
""",

    # Team 2 — Trick Room Medicham
    """\
Medicham @ Choice Band
Ability: Pure Power
Tera Type: Fighting
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- High Jump Kick
- Zen Headbutt
- Ice Punch
- Bullet Punch

Reuniclus @ Life Orb
Ability: Magic Guard
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Shadow Ball
- Focus Blast
- Trick Room

Hariyama @ Assault Vest
Ability: Guts
Tera Type: Fighting
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Close Combat
- Knock Off
- Bullet Punch
- Earthquake

Lycanroc-Dusk @ Choice Band
Ability: Tough Claws
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Close Combat
- Accelerock
- Fire Fang

Toedscruel @ Big Root
Ability: Mycelium Might
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Rapid Spin
- Leech Seed
- Giga Drain
- Earth Power

Araquanid @ Choice Band
Ability: Water Bubble
Tera Type: Water
EVs: 248 HP / 252 Atk / 8 SpD
Adamant Nature
- Liquidation
- Leech Life
- Lunge
- Poison Jab
""",

    # Team 3 — Lycanroc-Midnight Balance
    """\
Lycanroc-Midnight @ Choice Scarf
Ability: No Guard
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Stone Edge
- Close Combat
- Fire Fang
- Thunder Fang

Zangoose @ Toxic Orb
Ability: Toxic Boost
Tera Type: Normal
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Facade
- Quick Attack
- Close Combat
- Knock Off

Magneton @ Eviolite
Ability: Analytic
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Flash Cannon
- Volt Switch
- Thunder Wave

Tsareena @ Heavy-Duty Boots
Ability: Queenly Majesty
Tera Type: Grass
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Power Whip
- Knock Off
- Rapid Spin
- U-turn

Crabominable @ Choice Band
Ability: Iron Fist
Tera Type: Fighting
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Ice Hammer
- Close Combat
- Thunder Punch
- Earthquake

Mimikyu @ Life Orb
Ability: Disguise
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Play Rough
- Shadow Sneak
- Swords Dance
- Shadow Claw
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 NU
# ─────────────────────────────────────────────────────────────────────────────

GEN9NU = [

    # Team 1 — Eeveelution Balance
    """\
Vaporeon @ Leftovers
Ability: Water Absorb
Tera Type: Water
EVs: 252 HP / 252 Def / 4 SpA
Bold Nature
- Surf
- Aqua Ring
- Protect
- Scald

Jolteon @ Choice Specs
Ability: Volt Absorb
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Volt Switch
- Shadow Ball
- Thunder Wave

Sylveon @ Choice Specs
Ability: Pixilate
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hyper Voice
- Shadow Ball
- Psychic
- Psyshock

Umbreon @ Leftovers
Ability: Synchronize
Tera Type: Dark
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Foul Play
- Toxic
- Protect
- Moonlight

Espeon @ Life Orb
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Psyshock
- Shadow Ball
- Dazzling Gleam
- Calm Mind

Florges @ Leftovers
Ability: Flower Veil
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Moonblast
- Synthesis
- Wish
- Calm Mind
""",

    # Team 2 — Trick Room Slow Offense
    """\
Reuniclus @ Life Orb
Ability: Magic Guard
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Shadow Ball
- Focus Blast
- Trick Room

Palossand @ Leftovers
Ability: Water Compaction
Tera Type: Ghost
EVs: 252 HP / 4 SpA / 252 SpD
Sassy Nature
IVs: 0 Spe
- Shadow Ball
- Earth Power
- Stealth Rock
- Shore Up

Flareon @ Choice Band
Ability: Flash Fire
Tera Type: Fire
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Flare Blitz
- Quick Attack
- Body Slam
- Dig

Sableye @ Leftovers
Ability: Prankster
Tera Type: Dark
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
IVs: 0 Spe
- Foul Play
- Will-O-Wisp
- Recover
- Taunt

Araquanid @ Rocky Helmet
Ability: Water Bubble
Tera Type: Water
EVs: 248 HP / 8 Atk / 252 Def
Relaxed Nature
IVs: 0 Spe
- Liquidation
- Leech Life
- Wide Guard
- Poison Jab

Glaceon @ Choice Specs
Ability: Ice Body
Tera Type: Ice
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Blizzard
- Shadow Ball
- Water Pulse
- Icy Wind
""",

    # Team 3 — Sandslash-Alola Offensive
    """\
Sandslash-Alola @ Icicle Plate
Ability: Slush Rush
Tera Type: Ice
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Icicle Crash
- Iron Head
- Swords Dance
- Rapid Spin

Beartic @ Choice Band
Ability: Swift Swim
Tera Type: Ice
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Icicle Crash
- Superpower
- Liquidation
- Aqua Jet

Qwilfish-Hisui @ Black Sludge
Ability: Poison Point
Tera Type: Dark
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Barb Barrage
- Spikes
- Toxic Spikes
- Haze

Misdreavus @ Eviolite
Ability: Levitate
Tera Type: Ghost
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Shadow Ball
- Hex
- Will-O-Wisp
- Pain Split

Leafeon @ Life Orb
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Leaf Blade
- Knock Off
- Synthesis
- Swords Dance

Clefairy @ Eviolite
Ability: Magic Guard
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Moonblast
- Moonlight
- Thunder Wave
- Stealth Rock
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 PU
# ─────────────────────────────────────────────────────────────────────────────

GEN9PU = [

    # Team 1 — Ambipom Normal Spam
    """\
Ambipom @ Life Orb
Ability: Technician
Tera Type: Normal
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Double Hit
- Fake Out
- Last Resort
- Knock Off

Floatzel @ Choice Scarf
Ability: Swift Swim
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Waterfall
- Crunch
- Ice Punch
- Aqua Jet

Wigglytuff @ Leftovers
Ability: Cute Charm
Tera Type: Normal
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Hyper Voice
- Wish
- Protect
- Thunder Wave

Dunsparce @ Leftovers
Ability: Serene Grace
Tera Type: Normal
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Body Slam
- Glare
- Roost
- Stealth Rock

Appletun @ Leftovers
Ability: Thick Fat
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Sassy Nature
- Dragon Pulse
- Leech Seed
- Recover
- Apple Acid

Granbull @ Assault Vest
Ability: Intimidate
Tera Type: Fairy
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Play Rough
- Earthquake
- Close Combat
- Thunder Wave
""",

    # Team 2 — Trick Room Oranguru
    """\
Oranguru @ Leftovers
Ability: Inner Focus
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Trick Room
- Instruct
- Encore

Munchlax @ Eviolite
Ability: Thick Fat
Tera Type: Normal
EVs: 252 HP / 4 Def / 252 SpD
Sassy Nature
IVs: 0 Spe
- Body Slam
- Wish
- Protect
- Heal Bell

Flareon @ Choice Band
Ability: Flash Fire
Tera Type: Fire
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Flare Blitz
- Quick Attack
- Body Slam
- Dig

Furret @ Choice Band
Ability: Frisk
Tera Type: Normal
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Body Slam
- Knock Off
- Covet
- Sucker Punch

Granbull @ Flame Orb
Ability: Quick Feet
Tera Type: Fairy
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Play Rough
- Close Combat
- Earthquake
- Fire Punch

Decidueye-Hisui @ Leftovers
Ability: Long Reach
Tera Type: Ghost
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Triple Arrows
- Poltergeist
- Close Combat
- Rapid Spin
""",

    # Team 3 — Floatzel Rain Offense
    """\
Floatzel @ Life Orb
Ability: Swift Swim
Tera Type: Water
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Waterfall
- Ice Punch
- Crunch
- Aqua Jet

Sunflora @ Choice Specs
Ability: Chlorophyll
Tera Type: Grass
EVs: 252 SpA / 4 SpD / 252 Spe
Modest Nature
- Solar Beam
- Sludge Bomb
- Earth Power
- Weather Ball

Ambipom @ Normal Gem
Ability: Technician
Tera Type: Normal
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Fake Out
- Body Slam
- Double Hit
- Low Sweep

Dedenne @ Leftovers
Ability: Cheek Pouch
Tera Type: Electric
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Nuzzle
- Volt Switch
- Stealth Rock
- Super Fang

Wigglytuff @ Leftovers
Ability: Competitive
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Hyper Voice
- Stealth Rock
- Thunder Wave
- Wish

Smeargle @ Focus Sash
Ability: Own Tempo
Tera Type: Normal
EVs: 252 HP / 4 Def / 252 Spe
Timid Nature
- Encore
- Sticky Web
- Stealth Rock
- Spikes
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 ZU
# ─────────────────────────────────────────────────────────────────────────────

GEN9ZU = [

    # Team 1 — Serene Grace Spam
    """\
Dunsparce @ Leftovers
Ability: Serene Grace
Tera Type: Normal
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Body Slam
- Glare
- Roost
- Stealth Rock

Wigglytuff @ Leftovers
Ability: Cute Charm
Tera Type: Normal
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Hyper Voice
- Thunder Wave
- Wish
- Protect

Girafarig @ Life Orb
Ability: Inner Focus
Tera Type: Psychic
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Psychic
- Shadow Ball
- Nasty Plot
- Thunderbolt

Swalot @ Black Sludge
Ability: Liquid Ooze
Tera Type: Poison
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Sludge Bomb
- Recover
- Stealth Rock
- Toxic

Oranguru @ Leftovers
Ability: Inner Focus
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Careful Nature
- Foul Play
- Wish
- Protect
- Heal Bell

Granbull @ Assault Vest
Ability: Intimidate
Tera Type: Fairy
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Play Rough
- Earthquake
- Close Combat
- Thunder Wave
""",

    # Team 2 — Plusle/Minun Volt Turn
    """\
Plusle @ Life Orb
Ability: Plus
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Nasty Plot
- Dazzling Gleam
- Icy Wind

Minun @ Life Orb
Ability: Minus
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Thunderbolt
- Nasty Plot
- Dazzling Gleam
- Icy Wind

Swalot @ Black Sludge
Ability: Sticky Hold
Tera Type: Poison
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Sludge Bomb
- Encore
- Pain Split
- Toxic

Chimecho @ Leftovers
Ability: Levitate
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Psychic
- Heal Bell
- Wish
- Protect

Delibird @ Life Orb
Ability: Hustle
Tera Type: Ice
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Icicle Crash
- Ice Shard
- Aerial Ace
- Quick Attack

Furret @ Choice Scarf
Ability: Frisk
Tera Type: Normal
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Body Slam
- Knock Off
- Sucker Punch
- U-turn
""",

    # Team 3 — Oranguru Trick Room
    """\
Oranguru @ Leftovers
Ability: Inner Focus
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Trick Room
- Instruct
- Encore

Girafarig @ Choice Specs
Ability: Early Bird
Tera Type: Normal
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Psychic
- Shadow Ball
- Thunderbolt
- Nasty Plot

Granbull @ Flame Orb
Ability: Quick Feet
Tera Type: Fairy
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Play Rough
- Close Combat
- Earthquake
- Fire Punch

Delibird @ Life Orb
Ability: Hustle
Tera Type: Ice
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Icicle Crash
- Ice Shard
- Aerial Ace
- Quick Attack

Furret @ Silk Scarf
Ability: Frisk
Tera Type: Normal
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Body Slam
- Covet
- Sucker Punch
- Knock Off

Dunsparce @ Leftovers
Ability: Serene Grace
Tera Type: Normal
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Body Slam
- Headbutt
- Stealth Rock
- Roost
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 LC (Little Cup — Level 5, Eviolite, basic-stage Pokemon)
# ─────────────────────────────────────────────────────────────────────────────

GEN9LC = [

    # Team 1 — Mienfoo Offense
    """\
Mienfoo @ Eviolite
Ability: Regenerator
Level: 5
Tera Type: Fighting
EVs: 196 Atk / 36 Def / 36 SpD / 236 Spe
Jolly Nature
- High Jump Kick
- Knock Off
- U-turn
- Fake Out

Pawniard @ Eviolite
Ability: Defiant
Level: 5
Tera Type: Dark
EVs: 236 Atk / 36 Def / 236 Spe
Adamant Nature
- Iron Head
- Knock Off
- Sucker Punch
- Stealth Rock

Abra @ Life Orb
Ability: Inner Focus
Level: 5
Tera Type: Psychic
EVs: 236 SpA / 36 SpD / 236 Spe
Timid Nature
- Psychic
- Shadow Ball
- Energy Ball
- Dazzling Gleam

Larvitar @ Eviolite
Ability: Guts
Level: 5
Tera Type: Rock
EVs: 236 Atk / 36 Def / 236 Spe
Adamant Nature
- Stone Edge
- Earthquake
- Dragon Dance
- Crunch

Elekid @ Life Orb
Ability: Static
Level: 5
Tera Type: Electric
EVs: 236 SpA / 36 SpD / 236 Spe
Timid Nature
- Thunderbolt
- Ice Punch
- Cross Chop
- Psychic

Slowpoke @ Eviolite
Ability: Regenerator
Level: 5
Tera Type: Water
EVs: 36 HP / 236 SpA / 236 SpD
Quiet Nature
- Surf
- Psychic
- Fire Blast
- Slack Off
""",

    # Team 2 — Trick Room Timburr
    """\
Timburr @ Eviolite
Ability: Guts
Level: 5
Tera Type: Fighting
EVs: 236 HP / 236 Atk / 36 SpD
Brave Nature
IVs: 0 Spe
- Drain Punch
- Knock Off
- Mach Punch
- Bulk Up

Drifloon @ Oran Berry
Ability: Unburden
Level: 5
Tera Type: Flying
EVs: 36 HP / 236 SpA / 236 Spe
Modest Nature
- Shadow Ball
- Thunderbolt
- Will-O-Wisp
- Trick Room

Bronzor @ Eviolite
Ability: Levitate
Level: 5
Tera Type: Steel
EVs: 228 HP / 60 Def / 188 SpD
Sassy Nature
IVs: 0 Atk / 0 Spe
- Trick Room
- Gyro Ball
- Flash Cannon
- Stealth Rock

Munchlax @ Eviolite
Ability: Thick Fat
Level: 5
Tera Type: Normal
EVs: 196 HP / 116 Def / 196 SpD
Sassy Nature
IVs: 0 Spe
- Body Slam
- Earthquake
- Fire Punch
- Whirlwind

Magnemite @ Eviolite
Ability: Magnet Pull
Level: 5
Tera Type: Electric
EVs: 196 HP / 236 SpA / 76 SpD
Quiet Nature
IVs: 0 Spe
- Thunderbolt
- Flash Cannon
- Volt Switch
- Thunder Wave

Cottonee @ Eviolite
Ability: Prankster
Level: 5
Tera Type: Grass
EVs: 196 HP / 36 Def / 236 SpD / 36 Spe
Bold Nature
- Giga Drain
- Encore
- Stun Spore
- Memento
""",

    # Team 3 — Dratini Dragon
    """\
Dratini @ Eviolite
Ability: Marvel Scale
Level: 5
Tera Type: Dragon
EVs: 196 HP / 236 Atk / 76 Spe
Adamant Nature
- Extreme Speed
- Dragon Dance
- Wrap
- Fire Punch

Snorunt @ Eviolite
Ability: Ice Body
Level: 5
Tera Type: Ice
EVs: 236 SpA / 36 SpD / 236 Spe
Timid Nature
- Blizzard
- Shadow Ball
- Spikes
- Ice Shard

Magby @ Life Orb
Ability: Vital Spirit
Level: 5
Tera Type: Fire
EVs: 236 SpA / 36 SpD / 236 Spe
Timid Nature
- Fire Blast
- Thunderbolt
- Cross Chop
- Icy Wind

Pawniard @ Eviolite
Ability: Defiant
Level: 5
Tera Type: Dark
EVs: 236 Atk / 36 Def / 236 Spe
Adamant Nature
- Sucker Punch
- Iron Head
- Knock Off
- Stealth Rock

Bunnelby @ Choice Scarf
Ability: Huge Power
Level: 5
Tera Type: Normal
EVs: 236 Atk / 36 Def / 236 Spe
Jolly Nature
- Body Slam
- Quick Attack
- U-turn
- Bounce

Elekid @ Life Orb
Ability: Static
Level: 5
Tera Type: Electric
EVs: 236 SpA / 36 SpD / 236 Spe
Timid Nature
- Thunderbolt
- Ice Punch
- Cross Chop
- Psychic
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Doubles Ubers
# ─────────────────────────────────────────────────────────────────────────────

GEN9DOUBLESUBERS = [

    # Team 1 — Calyrex-Shadow + Miraidon Hyper Offense
    """\
Calyrex-Shadow @ Choice Scarf
Ability: As One (Spectrier)
Tera Type: Ghost
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Astral Barrage
- Psyshock
- Energy Ball
- Protect

Miraidon @ Choice Specs
Ability: Hadron Engine
Tera Type: Electric
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Electro Drift
- Draco Meteor
- Overheat
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Flutter Mane @ Life Orb
Ability: Protosynthesis
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Moonblast
- Shadow Ball
- Dazzling Gleam
- Protect

Rillaboom @ Assault Vest
Ability: Grassy Surge
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Grassy Glide
- Fake Out
- U-turn
- Wood Hammer

Amoonguss @ Rocky Helmet
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Spore
- Pollen Puff
- Rage Powder
- Protect
""",

    # Team 2 — Kyogre + Yveltal Rain
    """\
Kyogre @ Choice Scarf
Ability: Drizzle
Tera Type: Water
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Water Spout
- Origin Pulse
- Ice Beam
- Thunder

Eternatus @ Choice Specs
Ability: Pressure
Tera Type: Poison
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Dynamax Cannon
- Shadow Ball
- Flamethrower
- Protect

Tornadus-Therian @ Focus Sash
Ability: Regenerator
Tera Type: Flying
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Hurricane
- Taunt
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Landorus-Therian @ Rocky Helmet
Ability: Intimidate
Tera Type: Ground
EVs: 252 HP / 4 Atk / 252 Def
Impish Nature
- Earthquake
- Rock Slide
- U-turn
- Protect

Indeedee-F @ Psychic Seed
Ability: Psychic Surge
Tera Type: Psychic
EVs: 252 HP / 4 SpA / 252 SpD
Calm Nature
- Psychic
- Follow Me
- Healing Wish
- Protect
""",

    # Team 3 — Groudon + Calyrex-Ice Trick Room
    """\
Calyrex-Ice @ Weakness Policy
Ability: As One (Glastrier)
Tera Type: Ice
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Glacial Lance
- High Horsepower
- Close Combat
- Protect

Groudon @ Leftovers
Ability: Drought
Tera Type: Ground
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Precipice Blades
- Fire Punch
- Rock Slide
- Protect

Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Protect

Incineroar @ Sitrus Berry
Ability: Intimidate
Tera Type: Fire
EVs: 252 HP / 4 Atk / 252 SpD
Sassy Nature
IVs: 0 Spe
- Fake Out
- Flare Blitz
- Knock Off
- Protect

Necrozma-Dusk-Mane @ Power Herb
Ability: Prism Armor
Tera Type: Steel
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Sunsteel Strike
- Rock Slide
- Photon Geyser
- Protect

Amoonguss @ Coba Berry
Ability: Regenerator
Tera Type: Grass
EVs: 252 HP / 4 Def / 252 SpD
Sassy Nature
IVs: 0 Spe
- Spore
- Rage Powder
- Pollen Puff
- Protect
""",

]

# ─────────────────────────────────────────────────────────────────────────────
# Gen 9 Doubles UU
# ─────────────────────────────────────────────────────────────────────────────

GEN9DOUBLESUU = [

    # Team 1 — Hatterene Trick Room
    """\
Hatterene @ Misty Seed
Ability: Magic Bounce
Tera Type: Psychic
EVs: 252 HP / 252 SpA / 4 SpD
Quiet Nature
IVs: 0 Spe
- Psychic
- Mystical Fire
- Trick Room
- Healing Wish

Garganacl @ Sitrus Berry
Ability: Purifying Salt
Tera Type: Rock
EVs: 252 HP / 252 Atk / 4 Def
Brave Nature
IVs: 0 Spe
- Rock Slide
- Body Press
- Salt Cure
- Protect

Iron Hands @ Assault Vest
Ability: Quark Drive
Tera Type: Electric
EVs: 252 HP / 252 Atk / 4 SpD
Brave Nature
IVs: 0 Spe
- Close Combat
- Wild Charge
- Thunder Punch
- Fake Out

Slowking @ Assault Vest
Ability: Regenerator
Tera Type: Water
EVs: 252 HP / 4 SpA / 252 SpD
Sassy Nature
IVs: 0 Spe
- Surf
- Flamethrower
- Future Sight
- Ice Beam

Mimikyu @ Life Orb
Ability: Disguise
Tera Type: Fairy
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Play Rough
- Shadow Sneak
- Swords Dance
- Protect

Sylveon @ Choice Specs
Ability: Pixilate
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hyper Voice
- Icy Wind
- Shadow Ball
- Protect
""",

    # Team 2 — Togekiss Tailwind Offense
    """\
Togekiss @ Leftovers
Ability: Serene Grace
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Air Slash
- Follow Me
- Protect

Talonflame @ Life Orb
Ability: Gale Wings
Tera Type: Flying
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Brave Bird
- Flare Blitz
- Quick Attack
- Protect

Arcanine-Hisui @ Choice Band
Ability: Rock Head
Tera Type: Rock
EVs: 252 Atk / 4 Def / 252 Spe
Adamant Nature
- Head Smash
- Flare Blitz
- Close Combat
- Extreme Speed

Tsareena @ Assault Vest
Ability: Queenly Majesty
Tera Type: Grass
EVs: 252 HP / 252 Atk / 4 Spe
Adamant Nature
- Power Whip
- High Jump Kick
- Triple Axel
- Rapid Spin

Klefki @ Light Clay
Ability: Prankster
Tera Type: Steel
EVs: 252 HP / 4 Def / 252 SpD
Calm Nature
- Light Screen
- Reflect
- Thunder Wave
- Fairy Lock

Dusclops @ Eviolite
Ability: Frisk
Tera Type: Ghost
EVs: 252 HP / 4 Def / 252 SpD
Sassy Nature
IVs: 0 Spe
- Will-O-Wisp
- Trick Room
- Pain Split
- Night Shade
""",

    # Team 3 — Whimsicott + Sylveon Fairy Offense
    """\
Whimsicott @ Focus Sash
Ability: Prankster
Tera Type: Fairy
EVs: 252 HP / 4 SpA / 252 Spe
Timid Nature
- Tailwind
- Moonblast
- Encore
- Protect

Sylveon @ Choice Specs
Ability: Pixilate
Tera Type: Fairy
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Hyper Voice
- Icy Wind
- Shadow Ball
- Protect

Iron Hands @ Assault Vest
Ability: Quark Drive
Tera Type: Fighting
EVs: 252 HP / 252 Atk / 4 SpD
Adamant Nature
- Close Combat
- Wild Charge
- Thunder Punch
- Fake Out

Garganacl @ Leftovers
Ability: Purifying Salt
Tera Type: Rock
EVs: 252 HP / 4 Atk / 252 SpD
Careful Nature
- Rock Slide
- Body Press
- Wide Guard
- Protect

Tsareena @ Choice Band
Ability: Queenly Majesty
Tera Type: Grass
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Power Whip
- High Jump Kick
- Triple Axel
- U-turn

Mimikyu @ Life Orb
Ability: Disguise
Tera Type: Ghost
EVs: 252 Atk / 4 Def / 252 Spe
Jolly Nature
- Play Rough
- Shadow Claw
- Shadow Sneak
- Protect
""",

]

# Best-of-3 aliases (same team pools as their base formats)
GEN9VGC2026REGFBO3 = GEN9VGC2026REGF
GEN9VGC2026REGIBO3 = GEN9VGC2026REGI

# ─────────────────────────────────────────────────────────────────────────────
# Format → team list mapping
# ─────────────────────────────────────────────────────────────────────────────

FORMAT_TEAMS: dict[str, list[str]] = {
    "gen9ou"               : GEN9OU,
    "gen9nationaldex"      : GEN9NATIONALDEX,
    "gen9monotype"         : GEN9MONOTYPE,
    "gen9anythinggoes"     : GEN9ANYTHINGGOES,
    "gen9doublesou"        : GEN9DOUBLESOU,
    "gen9vgc2026regi"      : GEN9VGC2026REGI,
    "gen9vgc2026regf"      : GEN9VGC2026REGF,
    "gen9ubers"            : GEN9UBERS,
    "gen9uu"               : GEN9UU,
    "gen9ru"               : GEN9RU,
    "gen9nu"               : GEN9NU,
    "gen9pu"               : GEN9PU,
    "gen9zu"               : GEN9ZU,
    "gen9lc"               : GEN9LC,
    "gen9doublesubers"     : GEN9DOUBLESUBERS,
    "gen9doublesuu"        : GEN9DOUBLESUU,
    "gen9vgc2026regfbo3"   : GEN9VGC2026REGFBO3,
    "gen9vgc2026regibo3"   : GEN9VGC2026REGIBO3,
}
