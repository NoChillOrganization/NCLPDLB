"""Ollama fine-tuning workflow: dataset prep, Modelfile generation, team generation via local Ollama."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx

from ml.export import TrainingDataExporter

_DEFAULT_OLLAMA_URL = "http://localhost:11434"


async def prepare_dataset(regulation: Optional[str], output_dir: str) -> Path:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(output_dir) / f"finetune_{regulation or 'all'}.jsonl"
    exporter = TrainingDataExporter()
    await exporter.export_ollama_finetune(str(output_path))
    return output_path


def create_modelfile(base_model: str = "llama3", output_path: str = "Modelfile") -> Path:
    content = f"""FROM {base_model}
SYSTEM "You are a competitive Pokemon VGC team builder. You generate complete, legal, \
tournament-caliber 6-Pokemon teams in Showdown export format based on the requested regulation."
PARAMETER temperature 0.8
PARAMETER top_p 0.9
"""
    path = Path(output_path)
    path.write_text(content)
    return path


class OllamaClient:
    def __init__(self, base_url: str = _DEFAULT_OLLAMA_URL):
        self.base_url = base_url.rstrip("/")

    async def generate(self, model: str, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate", json={"model": model, "prompt": prompt, "stream": False}
            )
            resp.raise_for_status()
            return resp.json().get("response", "")


async def generate_team(client: OllamaClient, regulation: str, constraints: Optional[str] = None, model: str = "pokemon-vgc") -> str:
    prompt = f"Build me a {regulation} VGC team."
    if constraints:
        prompt += f" Constraints: {constraints}"
    return await client.generate(model, prompt)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--regulation", default=None)
    parser.add_argument("--output-dir", default="data/finetune")
    parser.add_argument("--base-model", default="llama3")
    args = parser.parse_args()

    dataset_path = asyncio.run(prepare_dataset(args.regulation, args.output_dir))
    modelfile_path = create_modelfile(args.base_model, f"{args.output_dir}/Modelfile")
    print(f"Dataset: {dataset_path}")
    print(f"Modelfile: {modelfile_path}")
    print(f"Next: ollama create pokemon-vgc -f {modelfile_path}")
