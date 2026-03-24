"""
Model A — Matchup Win Predictor.

Given two teams' species IDs, predict which player wins.
Uses a gradient-boosted classifier (scikit-learn) with embedding-based features.

Training pipeline:
  1. Load X_team / y_team from feature_extractor output
  2. Embed each species ID → learned vector (via sklearn's label encoding + one-hot)
  3. Train GradientBoostingClassifier with cross-validated hyperparameter search
  4. Evaluate accuracy, ROC-AUC, log-loss
  5. Save model to data/ml/<format>/matchup_model.pkl

Usage:
    # Single format
    python -m src.ml.train_matchup --format gen9ou

    # All formats with data
    python -m src.ml.train_matchup --all

    # Combined model across all formats
    python -m src.ml.train_matchup --all --combined
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score

log = logging.getLogger(__name__)

ML_DIR   = Path("data/ml")
TEAM_SIZE = 6


# ── Embedding layer ───────────────────────────────────────────────────────────

def _embed_team_matrix(X: np.ndarray, vocab_size: int) -> np.ndarray:
    """
    Convert raw species ID matrix (shape: n × 12) into a richer feature matrix.

    For each game we produce:
      - Presence vector: one-hot OR binary species presence (vocab_size × 2 dims)
      - Team overlap count (how many species are shared between teams)
      - Slot positions as fractional values

    Simple version: binary presence bags for each team, concatenated.
    This lets the model learn per-species win rates without needing embeddings.
    """
    n = X.shape[0]
    p1_cols = X[:, :TEAM_SIZE]    # (n, 6)
    p2_cols = X[:, TEAM_SIZE:]    # (n, 6)

    # Binary presence bags
    p1_bag = np.zeros((n, vocab_size), dtype=np.float32)
    p2_bag = np.zeros((n, vocab_size), dtype=np.float32)

    for i in range(TEAM_SIZE):
        p1_ids = p1_cols[:, i]
        p2_ids = p2_cols[:, i]
        valid_p1 = p1_ids > 0
        valid_p2 = p2_ids > 0
        p1_bag[np.arange(n)[valid_p1], p1_ids[valid_p1]] = 1.0
        p2_bag[np.arange(n)[valid_p2], p2_ids[valid_p2]] = 1.0

    # Symmetric difference — what's unique to each team
    p1_unique = p1_bag - p2_bag
    p2_unique = p2_bag - p1_bag

    # Overlap
    overlap = (p1_bag * p2_bag).sum(axis=1, keepdims=True)

    return np.hstack([p1_bag, p2_bag, p1_unique, p2_unique, overlap])


# ── Training ──────────────────────────────────────────────────────────────────

def train_format(
    fmt: str,
    ml_dir: Path = ML_DIR,
    n_folds: int = 5,
) -> dict[str, Any]:
    """
    Train a matchup predictor for a single format.

    Returns a results dict with accuracy, roc_auc, log_loss and the model.
    """
    fmt_dir = ml_dir / fmt
    X_path  = fmt_dir / "X_team.npy"
    y_path  = fmt_dir / "y_team.npy"
    vocab_path = fmt_dir / "species_vocab.json"

    if not X_path.exists():
        log.warning(f"No team features for {fmt} — skipping")
        return {}

    X_raw = np.load(X_path)
    y     = np.load(y_path)

    if len(X_raw) < 50:
        log.warning(f"{fmt}: only {len(X_raw)} samples — skipping (need ≥50)")
        return {}

    # Load vocabulary size
    vocab_size = 512   # default
    if vocab_path.exists():
        vocab_data = json.loads(vocab_path.read_text(encoding="utf-8"))
        vocab_size = len(vocab_data.get("token2id", {}))

    log.info(f"{fmt}: {len(X_raw)} games, vocab_size={vocab_size}")

    # Feature engineering
    X = _embed_team_matrix(X_raw, vocab_size)
    log.info(f"{fmt}: feature matrix {X.shape}")

    # Model: gradient boosted trees
    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
    )

    # Cross-validated evaluation
    cv = StratifiedKFold(n_splits=min(n_folds, len(y) // 10), shuffle=True, random_state=42)

    acc_scores  = cross_val_score(model, X, y, cv=cv, scoring="accuracy",  n_jobs=-1)
    auc_scores  = cross_val_score(model, X, y, cv=cv, scoring="roc_auc",   n_jobs=-1)
    loss_scores = -cross_val_score(model, X, y, cv=cv, scoring="neg_log_loss", n_jobs=-1)

    results = {
        "format":    fmt,
        "n_samples": len(X_raw),
        "accuracy":  float(acc_scores.mean()),
        "accuracy_std": float(acc_scores.std()),
        "roc_auc":   float(auc_scores.mean()),
        "roc_auc_std": float(auc_scores.std()),
        "log_loss":  float(loss_scores.mean()),
    }

    log.info(
        f"{fmt}: acc={results['accuracy']:.3f}±{results['accuracy_std']:.3f}  "
        f"auc={results['roc_auc']:.3f}±{results['roc_auc_std']:.3f}  "
        f"logloss={results['log_loss']:.3f}"
    )

    # Final fit on all data
    model.fit(X, y)
    results["model"] = model
    results["vocab_size"] = vocab_size

    # Save
    model_path = fmt_dir / "matchup_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "vocab_size": vocab_size, "format": fmt}, f)
    log.info(f"Saved model → {model_path}")

    # Save metrics (without the model object)
    metrics = {k: v for k, v in results.items() if k != "model"}
    (fmt_dir / "matchup_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    return results


def train_combined(
    formats: list[str],
    ml_dir: Path = ML_DIR,
    n_folds: int = 5,
) -> dict[str, Any]:
    """
    Train a single cross-format model by merging all format datasets.
    Species IDs are re-mapped to a global vocabulary.
    """
    all_X, all_y = [], []
    global_vocab: dict[str, int] = {"<UNK>": 0}

    for fmt in formats:
        fmt_dir    = ml_dir / fmt
        X_path     = fmt_dir / "X_team.npy"
        y_path     = fmt_dir / "y_team.npy"
        vocab_path = fmt_dir / "species_vocab.json"

        if not X_path.exists():
            continue

        X_raw = np.load(X_path)
        y_raw = np.load(y_path)

        if len(X_raw) < 20:
            continue

        # Remap species IDs to global vocab
        if vocab_path.exists():
            local_vocab = json.loads(vocab_path.read_text(encoding="utf-8"))["token2id"]
            id_map = {}
            for token, local_id in local_vocab.items():
                if token not in global_vocab:
                    global_vocab[token] = len(global_vocab)
                id_map[local_id] = global_vocab[token]
            remap = np.vectorize(lambda x: id_map.get(int(x), 0))
            X_remapped = remap(X_raw)
        else:  # pragma: no cover
            X_remapped = X_raw

        all_X.append(X_remapped)
        all_y.append(y_raw)

    if not all_X:
        log.error("No data found for combined model")
        return {}

    X_combined = np.vstack(all_X)
    y_combined = np.concatenate(all_y)
    vocab_size  = len(global_vocab)
    log.info(f"Combined: {len(X_combined)} games, {vocab_size} species in vocab")

    X = _embed_team_matrix(X_combined.astype(np.int32), vocab_size)

    model = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        min_samples_leaf=5,
        random_state=42,
    )

    cv = StratifiedKFold(n_splits=min(n_folds, len(y_combined) // 50), shuffle=True, random_state=42)
    acc_scores = cross_val_score(model, X, y_combined, cv=cv, scoring="accuracy", n_jobs=-1)
    auc_scores = cross_val_score(model, X, y_combined, cv=cv, scoring="roc_auc",  n_jobs=-1)

    results = {
        "format":    "combined",
        "n_samples": len(X_combined),
        "accuracy":  float(acc_scores.mean()),
        "accuracy_std": float(acc_scores.std()),
        "roc_auc":   float(auc_scores.mean()),
        "roc_auc_std": float(auc_scores.std()),
        "vocab_size": vocab_size,
    }
    log.info(
        f"Combined: acc={results['accuracy']:.3f}±{results['accuracy_std']:.3f}  "
        f"auc={results['roc_auc']:.3f}±{results['roc_auc_std']:.3f}"
    )

    model.fit(X, y_combined)
    results["model"] = model

    combined_dir = ml_dir / "combined"
    combined_dir.mkdir(exist_ok=True)

    with open(combined_dir / "matchup_model.pkl", "wb") as f:
        pickle.dump({"model": model, "vocab_size": vocab_size, "global_vocab": global_vocab}, f)
    (combined_dir / "global_vocab.json").write_text(
        json.dumps({"token2id": global_vocab}, indent=2), encoding="utf-8"
    )
    metrics = {k: v for k, v in results.items() if k != "model"}
    (combined_dir / "matchup_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    log.info(f"Saved combined model → {combined_dir}/matchup_model.pkl")
    return results


# ── Inference helper ──────────────────────────────────────────────────────────

def predict_matchup(
    p1_team: list[str],
    p2_team: list[str],
    fmt: str = "gen9ou",
    ml_dir: Path = ML_DIR,
) -> dict[str, float]:
    """
    Predict win probability for a matchup.

    Args:
        p1_team: list of species names for player 1
        p2_team: list of species names for player 2
        fmt:     format to use (loads that format's model)

    Returns:
        {"p1_win_prob": 0.62, "p2_win_prob": 0.38}
    """
    fmt_dir    = ml_dir / fmt
    model_path = fmt_dir / "matchup_model.pkl"
    vocab_path = fmt_dir / "species_vocab.json"

    if not model_path.exists():
        raise FileNotFoundError(f"No trained model for format '{fmt}'. Run train_matchup first.")

    with open(model_path, "rb") as f:
        bundle = pickle.load(f)
    model      = bundle["model"]
    vocab_size = bundle["vocab_size"]

    vocab: dict[str, int] = {}
    if vocab_path.exists():
        vocab = json.loads(vocab_path.read_text(encoding="utf-8"))["token2id"]

    def to_ids(team: list[str]) -> list[int]:
        ids = [vocab.get(s.lower().strip(), 0) for s in team[:TEAM_SIZE]]
        while len(ids) < TEAM_SIZE:
            ids.append(0)
        return ids

    X_raw = np.array([to_ids(p1_team) + to_ids(p2_team)], dtype=np.int32)
    X     = _embed_team_matrix(X_raw, vocab_size)
    proba = model.predict_proba(X)[0]

    return {"p1_win_prob": float(proba[1]), "p2_win_prob": float(proba[0])}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Train matchup prediction models")
    ap.add_argument("--format",   default="gen9ou", help="Single format to train")
    ap.add_argument("--all",      action="store_true", help="Train all formats with data")
    ap.add_argument("--combined", action="store_true", help="Also train a combined cross-format model")
    ap.add_argument("--ml-dir",   default="data/ml", help="ML data directory")
    args = ap.parse_args()

    ml_dir = Path(args.ml_dir)

    if args.all or args.combined:
        formats = [d.name for d in ml_dir.iterdir()
                   if d.is_dir() and (d / "X_team.npy").exists() and d.name != "combined"]
        formats.sort()
        print(f"\nFormats with data: {formats}\n")
    else:
        formats = [args.format]

    all_results = []
    for fmt in formats:
        r = train_format(fmt, ml_dir=ml_dir)
        if r:
            all_results.append(r)

    if args.combined and len(formats) > 1:
        print("\nTraining combined cross-format model...")
        train_combined(formats, ml_dir=ml_dir)

    print("\n" + "=" * 60)
    print(f"{'Format':<30} {'Samples':>8} {'Accuracy':>10} {'ROC-AUC':>10}")
    print("-" * 60)
    for r in sorted(all_results, key=lambda x: -x.get("accuracy", 0)):
        print(
            f"{r['format']:<30} {r['n_samples']:>8} "
            f"{r['accuracy']:>9.1%} "
            f"{r['roc_auc']:>9.3f}"
        )
