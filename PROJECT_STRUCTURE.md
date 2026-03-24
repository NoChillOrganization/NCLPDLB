# Project Structure — NCLPDLB

## Root Directory
- `.gemini/`: AI-specific configurations and tracking.
- `.planning/`: High-level roadmap, state, and milestone tracking.
- `docs/`: Project documentation and guidelines.
- `scripts/`: Utility scripts (e.g., test runners, data collectors).
- `src/`: Core source code.
- `tests/`: Comprehensive test suite.
- `STATUS.md`: Current build status, test coverage, and active work.
- `ROADMAP.md`: Long-term goals and phase-based planning.

## Source Code (`src/`)
- `bot/`: Discord bot implementation.
    - `constants.py`: Bot configurations and format maps.
    - `views/`: Discord UI components (e.g., `team_import_view.py`).
- `data/`: Data persistence and logic.
    - `models.py`: Database schemas.
    - `services/`: Business logic (e.g., team parsing).
- `ml/`: Machine Learning and Reinforcement Learning.
    - `battle_env.py`: Gymnasium wrapper for poke-env.
- `utils/`: Common utilities.

## Planning (`.planning/`)
- `STATE.md`: Detailed status of current milestones and phases.
- `ROADMAP.md`: Living document of project phases.
