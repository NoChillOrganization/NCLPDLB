"""
Transformer-based Policy / Value Model.

Architecture
------------
  Input  : sequence of battle state vectors, shape (T, OBS_DIM)
            T = sequence length (history of turns; T=1 for single-step inference)
  Encoder: positional embedding → N × TransformerEncoderLayer (multi-head attn + FFN)
  Heads  : policy head → logits over action space (Discrete 26)
            value head  → scalar state value estimate

Designed for:
  • CPU-friendly training on Windows (no CUDA required)
  • Low memory footprint (configurable depth / width)
  • Direct integration with the MCTS engine (value + policy in one forward pass)
  • Compatibility with the custom training loop in trainer.py

Usage
-----
  from src.ml.transformer_model import BattleTransformer, load_model, save_model

  # Build model
  model = BattleTransformer()                     # default config
  model = BattleTransformer(n_actions=26, d_model=64, n_heads=4, n_layers=2)

  # Forward pass — single timestep (MCTS inference)
  obs = torch.zeros(1, 1, 48)   # (batch=1, seq_len=1, OBS_DIM=48)
  policy_logits, value = model(obs)
  # policy_logits: (1, 26)   value: (1, 1)

  # Forward pass — sequence of turns (training)
  obs_seq = torch.zeros(8, 10, 48)   # (batch=8, seq_len=10, OBS_DIM=48)
  policy_logits, value = model(obs_seq)
  # policy_logits: (8, 26)  value: (8, 1)  (last timestep used)

  # Save / load
  save_model(model, "models/latest.pt")
  model = load_model("models/latest.pt")
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import torch
    import torch.nn as nn
    TORCH_OK = True
except ImportError:  # pragma: no cover
    TORCH_OK = False
    torch = None  # type: ignore
    nn = None     # type: ignore

from src.ml.battle_env import OBS_DIM, N_ACTIONS_GEN9  # noqa: E402


# ── Positional encoding ───────────────────────────────────────────────────────

class _PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding — works for any sequence length."""

    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        # Precompute sinusoidal table
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)   # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        """x: (batch, seq_len, d_model)"""
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)


# ── Main model ────────────────────────────────────────────────────────────────

class BattleTransformer(nn.Module):
    """
    Lightweight Transformer policy + value network for Pokemon battles.

    Parameters
    ----------
    obs_dim    : input feature size per timestep (default: OBS_DIM = 48)
    n_actions  : size of action space (default: N_ACTIONS_GEN9 = 26)
    d_model    : transformer hidden dimension (default: 64)
    n_heads    : number of attention heads (default: 4)
    n_layers   : number of TransformerEncoder layers (default: 2)
    ffn_dim    : feed-forward inner dimension (default: 128)
    dropout    : dropout rate (default: 0.1)
    max_seq    : maximum turn history length (default: 64)
    """

    def __init__(
        self,
        obs_dim: int = OBS_DIM,
        n_actions: int = N_ACTIONS_GEN9,
        d_model: int = 64,
        n_heads: int = 4,
        n_layers: int = 2,
        ffn_dim: int = 128,
        dropout: float = 0.1,
        max_seq: int = 64,
    ) -> None:
        super().__init__()
        if not TORCH_OK:  # pragma: no cover
            raise ImportError(
                "PyTorch is required. Install it from https://pytorch.org/get-started/locally/"
            )

        self.obs_dim   = obs_dim
        self.n_actions = n_actions
        self.d_model   = d_model

        # Input projection: obs_dim → d_model
        self.input_proj = nn.Linear(obs_dim, d_model)

        # Positional encoding
        self.pos_enc = _PositionalEncoding(d_model, max_len=max_seq, dropout=dropout)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=ffn_dim,
            dropout=dropout,
            batch_first=True,    # (batch, seq, d_model)
            norm_first=True,     # Pre-LN for training stability on CPU
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer=encoder_layer,
            num_layers=n_layers,
        )

        # Policy head: d_model → n_actions (logits)
        self.policy_head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, n_actions),
        )

        # Value head: d_model → 1 scalar
        self.value_head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, 1),
        )

        self._init_weights()

    # ── Weight init ─────────────────────────────────────────────────────

    def _init_weights(self) -> None:
        """Xavier uniform init for all linear layers."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    # ── Forward ─────────────────────────────────────────────────────────

    def forward(
        self,
        obs: "torch.Tensor",
        mask: "torch.Tensor | None" = None,
    ) -> tuple["torch.Tensor", "torch.Tensor"]:
        """
        Args:
            obs  : float32 tensor (batch, seq_len, obs_dim)
            mask : optional bool tensor (batch, seq_len) — True = padding to ignore

        Returns:
            policy_logits : (batch, n_actions)  — unnormalized action scores
            value         : (batch, 1)           — state value estimate
        """
        # Project input to model dimension
        x = self.input_proj(obs)       # (batch, seq, d_model)
        x = self.pos_enc(x)            # add positional encoding

        # Encode sequence
        if mask is not None:
            x = self.encoder(x, src_key_padding_mask=mask)
        else:
            x = self.encoder(x)        # (batch, seq, d_model)

        # Use the last timestep's representation for both heads
        last = x[:, -1, :]             # (batch, d_model)

        policy_logits = self.policy_head(last)   # (batch, n_actions)
        value         = self.value_head(last)    # (batch, 1)

        return policy_logits, value

    # ── Convenience inference methods ────────────────────────────────────

    def predict(
        self,
        obs_vec: "torch.Tensor | Any",
        legal_mask: "torch.Tensor | None" = None,
        temperature: float = 1.0,
    ) -> tuple[int, float]:
        """
        Single-step inference (no gradient).

        Args:
            obs_vec    : shape (obs_dim,) or (1, obs_dim) or (1, 1, obs_dim)
            legal_mask : bool tensor (n_actions,) — True = illegal action
            temperature: softmax temperature (1.0 = standard, <1 = sharper)

        Returns:
            action_id (int), value_estimate (float)
        """
        import torch as _torch
        self.eval()
        with _torch.no_grad():
            x = _torch.as_tensor(obs_vec, dtype=_torch.float32)
            # Normalise to (1, 1, obs_dim)
            if x.dim() == 1:
                x = x.unsqueeze(0).unsqueeze(0)
            elif x.dim() == 2:
                x = x.unsqueeze(0)

            logits, val = self.forward(x)  # (1, n_actions), (1, 1)

            if legal_mask is not None:
                logits = logits.masked_fill(legal_mask.unsqueeze(0), float("-inf"))

            if temperature != 1.0:
                logits = logits / temperature

            probs  = _torch.softmax(logits, dim=-1)
            action = int(_torch.argmax(probs, dim=-1).item())
            value  = float(val.squeeze().item())

        return action, value

    def policy_probs(
        self,
        obs_vec: "torch.Tensor | Any",
        legal_mask: "torch.Tensor | None" = None,
    ) -> "torch.Tensor":
        """
        Return the full policy probability distribution as a tensor (n_actions,).
        Illegal actions are masked to 0 probability.
        """
        import torch as _torch
        self.eval()
        with _torch.no_grad():
            x = _torch.as_tensor(obs_vec, dtype=_torch.float32)
            if x.dim() == 1:
                x = x.unsqueeze(0).unsqueeze(0)
            elif x.dim() == 2:
                x = x.unsqueeze(0)
            logits, _ = self.forward(x)
            if legal_mask is not None:
                logits = logits.masked_fill(legal_mask.unsqueeze(0), float("-inf"))
            return _torch.softmax(logits, dim=-1).squeeze(0)

    # ── Model info ───────────────────────────────────────────────────────

    def num_parameters(self) -> int:
        """Total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"BattleTransformer("
            f"obs_dim={self.obs_dim}, n_actions={self.n_actions}, "
            f"d_model={self.d_model}, params={self.num_parameters():,})"
        )


# ── Save / load helpers ───────────────────────────────────────────────────────

def save_model(model: "BattleTransformer", path: str | Path) -> None:
    """
    Save model weights + config to a .pt file.

    Saved dict structure:
        state_dict : model.state_dict()
        config     : constructor kwargs for reconstruction
    """
    import torch as _torch
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _torch.save({
        "state_dict": model.state_dict(),
        "config": {
            "obs_dim":   model.obs_dim,
            "n_actions": model.n_actions,
            "d_model":   model.d_model,
        },
    }, path)
    log.info("Model saved to %s  (%d params)", path, model.num_parameters())


def load_model(path: str | Path, device: str = "cpu") -> "BattleTransformer":
    """
    Load a BattleTransformer from a .pt checkpoint.

    Args:
        path   : path to the .pt file produced by save_model()
        device : torch device string (default "cpu")

    Returns:
        BattleTransformer with weights loaded, set to eval mode.
    """
    import torch as _torch
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {path}")

    data = _torch.load(path, map_location=device, weights_only=True)
    config = data.get("config", {})
    model = BattleTransformer(**config)
    model.load_state_dict(data["state_dict"])
    model.eval()
    log.info("Model loaded from %s", path)
    return model


def build_default_model() -> "BattleTransformer":
    """Return a fresh BattleTransformer with the default (CPU-friendly) config."""
    return BattleTransformer(
        obs_dim=OBS_DIM,
        n_actions=N_ACTIONS_GEN9,
        d_model=64,
        n_heads=4,
        n_layers=2,
        ffn_dim=128,
        dropout=0.1,
    )
