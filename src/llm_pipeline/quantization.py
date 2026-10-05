"""Shared quantization helpers for Hugging Face planner backends."""

from __future__ import annotations

from typing import Optional


VALID_QUANTIZATION_MODES = ("none", "bnb8", "bnb4")


def normalize_quantization(quantization: Optional[str] = None, *, use_4bit: bool = False) -> str:
    """Return a canonical quantization mode.

    ``use_4bit`` keeps the old boolean API working while newer server commands
    can use explicit modes.
    """
    value = (quantization or "").strip().lower().replace("-", "").replace("_", "")
    if not value:
        return "bnb4" if use_4bit else "none"
    aliases = {
        "no": "none",
        "none": "none",
        "fp16": "none",
        "bf16": "none",
        "float16": "none",
        "8bit": "bnb8",
        "bnb8": "bnb8",
        "bitsandbytes8": "bnb8",
        "4bit": "bnb4",
        "bnb4": "bnb4",
        "bitsandbytes4": "bnb4",
    }
    if value not in aliases:
        valid = ", ".join(VALID_QUANTIZATION_MODES)
        raise ValueError(f"Unsupported quantization mode '{quantization}'. Expected one of: {valid}.")
    return aliases[value]


def uses_4bit(quantization: str) -> bool:
    return normalize_quantization(quantization) == "bnb4"


def make_bnb_quantization_config(quantization: str, torch_module):
    """Build a BitsAndBytesConfig for bnb8/bnb4 modes."""
    mode = normalize_quantization(quantization)
    if mode == "none":
        return None

    from transformers import BitsAndBytesConfig

    if mode == "bnb8":
        return BitsAndBytesConfig(load_in_8bit=True)

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch_module.float16,
        bnb_4bit_use_double_quant=True,
    )
