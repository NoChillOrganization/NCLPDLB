"""Team placing predictor: feature extraction -> StandardScaler -> GradientBoostingClassifier."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_MODELS_DIR = Path(__file__).parent.parent / "models_trained"
_MODELS_DIR.mkdir(exist_ok=True)


class TeamPlacingPredictor:
    def __init__(self):
        self.pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                ("clf", GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=42)),
            ]
        )

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        self.pipeline.fit(X, y)

    def predict(self, team_json: list[dict]) -> dict:
        from ml.export import _load_or_build_vocab, _MOVE_VOCAB_PATH, _SPECIES_VOCAB_PATH

        species_vocab = _load_or_build_vocab(_SPECIES_VOCAB_PATH, set())
        move_vocab = _load_or_build_vocab(_MOVE_VOCAB_PATH, set())

        rows = []
        for mon in team_json:
            species_idx = species_vocab.get(mon.get("species"), 0)
            move_idxs = [move_vocab.get(m, 0) for m in (mon.get("moves") or [None] * 4)][:4]
            while len(move_idxs) < 4:
                move_idxs.append(0)
            evs = mon.get("evs") or {}
            ivs = mon.get("ivs") or {}
            rows.append(
                [species_idx]
                + move_idxs
                + [evs.get(k, 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")]
                + [ivs.get(k, 31) for k in ("hp", "atk", "def", "spa", "spd", "spe")]
            )
        X = np.array(rows, dtype=np.float64)
        proba = self.pipeline.predict_proba(X)
        avg_proba = proba.mean(axis=0)
        predicted_class = int(np.argmax(avg_proba))
        return {"placing_bucket": predicted_class, "confidence": float(avg_proba[predicted_class])}

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> dict:
        y_pred = self.pipeline.predict(X_test)
        return {
            "accuracy": accuracy_score(y_test, y_pred),
            "report": classification_report(y_test, y_pred, output_dict=True),
        }

    def save(self, regulation: Optional[str] = None) -> Path:
        path = _MODELS_DIR / f"classifier_{regulation or 'all'}.joblib"
        joblib.dump(self.pipeline, path)
        return path

    @classmethod
    def load(cls, regulation: Optional[str] = None) -> "TeamPlacingPredictor":
        # joblib.load executes pickle bytecode; safe here only because classifier_*.joblib
        # files are produced exclusively by this project's own save() above (models_trained/
        # is gitignored, never fetched from an external/untrusted source).
        path = _MODELS_DIR / f"classifier_{regulation or 'all'}.joblib"
        instance = cls()
        instance.pipeline = joblib.load(path)
        return instance


if __name__ == "__main__":  # pragma: no cover - standalone training entry point
    import argparse

    from ml.export import TrainingDataExporter
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--regulation", default=None)
    parser.add_argument("--matrix-path", default="data/feature_matrix.npz")
    args = parser.parse_args()

    exporter = TrainingDataExporter()
    asyncio.run(exporter.export_feature_matrix(args.matrix_path, args.regulation))

    data = np.load(args.matrix_path)
    X, y = data["X"], data["y_top16"]
    if len(X) < 10:
        print(f"Only {len(X)} rows exported — need more training data before this is meaningful.")
    else:
        predictor = TeamPlacingPredictor()
        predictor.train(X, y)
        path = predictor.save(args.regulation)
        print(f"Trained on {len(X)} rows, saved to {path}")
