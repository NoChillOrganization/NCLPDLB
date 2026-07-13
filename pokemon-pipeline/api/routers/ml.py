"""ML prediction endpoint — placing bucket prediction + similar teams for a given team paste/JSON."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tasks.process.parser import ShowdownPasteParser

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/predict")
async def predict(payload: dict) -> dict:
    """Body: {"raw_paste": "..."} or {"team_json": [...]}. Returns placing_bucket + confidence."""
    team_json = payload.get("team_json")
    if team_json is None:
        raw_paste = payload.get("raw_paste")
        if not raw_paste:
            raise HTTPException(status_code=422, detail="Provide either raw_paste or team_json")
        team_json = ShowdownPasteParser().parse(raw_paste)

    try:
        from ml.classifier import TeamPlacingPredictor

        predictor = TeamPlacingPredictor.load(payload.get("regulation"))
        prediction = predictor.predict(team_json)
    except FileNotFoundError:
        return {"error": "No trained classifier found for this regulation yet. Run ml/classifier.py first."}

    return prediction
