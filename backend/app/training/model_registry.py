"""Supported-model registry for QLoRA fine-tuning.

Each entry defines the HuggingFace model ID, hardware budget, LoRA
target modules, and chat template.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelConfig:
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


# Key = the base_model string the API accepts (matches hf_model_id).
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
    if model_id not in SUPPORTED_MODELS:
        supported = ", ".join(sorted(SUPPORTED_MODELS.keys()))
        raise ValueError(
            f"Unsupported model: '{model_id}'. Supported models: {supported}"
        )
    return SUPPORTED_MODELS[model_id]
