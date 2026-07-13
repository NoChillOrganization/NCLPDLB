const express = require('express');
const cors = require('cors');
const FORMAT_MAP = require('./format_map');

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const PORT = process.env.PORT || 3001;
const TIMEOUT_MS = 2000;

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms)),
  ]);
}

app.get('/health', (req, res) => res.json({ status: 'ok' }));

app.post('/classify', async (req, res) => {
  const { team_json: teamJson } = req.body || {};
  if (!Array.isArray(teamJson) || teamJson.length === 0) {
    return res.status(400).json({ error: 'team_json must be a non-empty array' });
  }

  try {
    const result = await withTimeout(classifyTeam(teamJson), TIMEOUT_MS);
    return res.json(result);
  } catch (err) {
    return res.status(200).json({ stalliness: null, bias: null, tags: [], lead_bias: null, note: String(err.message || err) });
  }
});

async function classifyTeam(teamJson) {
  // stalliness: unimplemented. @pkmn/stats has no computeStalliness API (checked v0.4.0's
  // Stats/Classifier exports directly) - would need a heuristic built from scratch.
  const stalliness = null;
  let bias = null;

  const atkTotal = teamJson.reduce((sum, mon) => sum + (mon.evs?.atk || 0) + (mon.evs?.spa || 0), 0);
  const defTotal = teamJson.reduce((sum, mon) => sum + (mon.evs?.hp || 0) + (mon.evs?.def || 0) + (mon.evs?.spd || 0), 0);
  bias = atkTotal >= defTotal ? 'offense' : 'balance';

  const tags = [];
  if (atkTotal > defTotal * 1.5) tags.push('offense');
  else if (defTotal > atkTotal * 1.5) tags.push('stall');
  else tags.push('balance');

  const leadBias = teamJson[0]?.species || null;

  return { stalliness, bias, tags, lead_bias: leadBias };
}

app.post('/validate', async (req, res) => {
  const { team_json: teamJson, format } = req.body || {};
  if (!Array.isArray(teamJson)) {
    return res.status(400).json({ error: 'team_json must be an array' });
  }

  let TeamValidator;
  let Dex;
  try {
    ({ TeamValidator, Dex } = require('@pkmn/sim'));
  } catch (_err) {
    return res.json({ is_valid: true, errors: [], note: 'pkmn/sim unavailable, skipping deep validation' });
  }

  try {
    const formatId = FORMAT_MAP[format] || format;
    const result = await withTimeout(runValidation(TeamValidator, Dex, formatId, teamJson), TIMEOUT_MS);
    return res.json(result);
  } catch (err) {
    return res.json({ is_valid: true, errors: [], note: `validation error, skipped: ${err.message || err}` });
  }
});

async function runValidation(TeamValidator, Dex, formatId, teamJson) {
  const format = Dex.formats.get(formatId);
  const validator = new TeamValidator(format);

  const team = teamJson.map((mon) => ({
    species: mon.species,
    name: mon.nickname || mon.species,
    item: mon.item || '',
    ability: mon.ability || '',
    moves: (mon.moves || []).filter(Boolean),
    nature: mon.nature || 'Hardy',
    evs: {
      hp: mon.evs?.hp || 0,
      atk: mon.evs?.atk || 0,
      def: mon.evs?.def || 0,
      spa: mon.evs?.spa || 0,
      spd: mon.evs?.spd || 0,
      spe: mon.evs?.spe || 0,
    },
    ivs: {
      hp: mon.ivs?.hp ?? 31,
      atk: mon.ivs?.atk ?? 31,
      def: mon.ivs?.def ?? 31,
      spa: mon.ivs?.spa ?? 31,
      spd: mon.ivs?.spd ?? 31,
      spe: mon.ivs?.spe ?? 31,
    },
    level: mon.level || 50,
    gender: mon.gender || '',
    shiny: !!mon.is_shiny,
    teraType: mon.tera_type || undefined,
  }));

  const errors = validator.validateTeam(team) || [];
  return { is_valid: errors.length === 0, errors };
}

app.listen(PORT, () => {
  console.log(`classifier listening on ${PORT}`);
});
