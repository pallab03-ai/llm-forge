"""Model registry for supported QLoRA fine-tuning models.

Each entry defines the HuggingFace model ID, hardware requirements,
LoRA target modules, and chat template configuration needed for
QLoRA training.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelConfig:
    """Immutable configuration for a supported model.

    Attributes:
        display_name: Human-readable model name.
        hf_model_id: HuggingFace model identifier (e.g. "google/gemma-3-1b-it").
        parameter_count: Number of parameters in billions (e.g. 1.0).
        quantized_vram_gb: Estimated VRAM in GB for 4-bit quantized inference + training.
        max_seq_length: Maximum sequence length the model supports.
        lora_target_modules: List of module names to attach LoRA adapters to.
        attn_implementation: Attention implementation ("eager", "sdpa", "flash_attention_2").
        torch_dtype: Torch dtype string for model loading (e.g. "float16").
        chat_template: Jinja-style chat template for formatting conversations.
        special_tokens: Dict of special token overrides (e.g. pad_token).
    """

    display_name: str
    hf_model_id: str
    parameter_count: float
    quantized_vram_gb: float
    max_seq_length: int
    lora_target_modules: list[str] = field(default_factory=list)
    attn_implementation: str = "eager"
    torch_dtype: str = "float16"
    chat_template: str = ""
    special_tokens: dict[str, str] = field(default_factory=dict)
    default_batch_size: int = 4
    recommended_seq_length: int = 2048


# ---------------------------------------------------------------------------
# Supported model registry
# ---------------------------------------------------------------------------
# Key = the `base_model` string that the API accepts (matches hf_model_id).

SUPPORTED_MODELS: dict[str, ModelConfig] = {
    "google/gemma-3-1b-it": ModelConfig(
        display_name="Gemma 3 1B IT",
        hf_model_id="google/gemma-3-1b-it",
        parameter_count=1.0,
        quantized_vram_gb=3.0,
        max_seq_length=8192,
        lora_target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        attn_implementation="eager",
        torch_dtype="float16",
        chat_template=(
            "<start_of_turn>user\n{instruction}\n{input}<end_of_turn>\n"
            "<start_of_turn>model\n{output}<end_of_turn>"
        ),
        special_tokens={"pad_token": "<eos>"},
        default_batch_size=4,
        recommended_seq_length=2048,
    ),
}


def get_model_config(model_id: str) -> ModelConfig:
    """Look up a model config by its HuggingFace model ID.

    Args:
        model_id: The model identifier string (e.g. "google/gemma-3-1b-it").

    Returns:
        The ModelConfig for the requested model.

    Raises:
        ValueError: If the model_id is not in the SUPPORTED_MODELS registry.
    """
    if model_id not in SUPPORTED_MODELS:
        supported = ", ".join(sorted(SUPPORTED_MODELS.keys()))
        raise ValueError(
            f"Unsupported model: '{model_id}'. Supported models: {supported}"
        )
    return SUPPORTED_MODELS[model_id]
