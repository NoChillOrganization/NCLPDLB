"""
src/ml — Machine Learning pipeline for Pokemon Draft League.

Modules:
  replay_scraper    — Download replays from Pokemon Showdown
  replay_parser     — Parse raw battle logs into structured BattleRecord objects
  feature_extractor — Convert BattleRecords into numpy feature vectors for ML
  models/           — Trained models (matchup predictor, battle policy)
"""
