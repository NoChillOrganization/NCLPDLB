# Ollama Fine-Tuning Workflow

Fine-tune a local LLM on top-16 tournament team pastes to generate new competitive teams.

## 1. Export training data

```bash
python -m ml.ollama_finetune --regulation "Reg M-B" --output-dir data/finetune
```

This writes `data/finetune/finetune_Reg M-B.jsonl` (one Ollama-format conversation per team) and
`data/finetune/Modelfile`.

## 2. Create the base Ollama model

```bash
ollama create pokemon-vgc -f data/finetune/Modelfile
```

## 3. Provide the JSONL to the fine-tuning API

Ollama's fine-tuning support varies by version — consult `ollama --help` / the Ollama docs for the
current fine-tune command for your installed version. The JSONL produced above is already in the
`{"messages": [...]}` conversation format most fine-tune tooling expects.

## 4. Test with generate_team()

```python
import asyncio
from ml.ollama_finetune import OllamaClient, generate_team

async def main():
    client = OllamaClient()
    team = await generate_team(client, "Reg M-B", constraints="must include Calyrex-Shadow")
    print(team)

asyncio.run(main())
```

Requires a local Ollama instance running at `http://localhost:11434` (default).
