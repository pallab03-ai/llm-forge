"""Phase 4.2 — QLoRA Training Engine.

Provides the core components for QLoRA fine-tuning:
- ModelConfig / SUPPORTED_MODELS registry
- DatasetNormalizer (CSV/JSON/JSONL → Alpaca JSONL)
- DatasetLoader (JSONL → HF Dataset)
- AlpacaFormatter (Alpaca → ### Instruction / ### Response)
- QLoRAConfigFactory (BitsAndBytesConfig, float16)
- PEFTConfigFactory (LoraConfig)
- TrainingArgumentsFactory (TRL TrainingArguments)
- ArtifactValidator (4-file artifact check)

Heavy ML dependencies (torch, transformers, peft, trl) are imported
lazily inside factory methods, so the package can be imported without
those packages installed (e.g. in test environments).
"""

from app.training.model_registry import ModelConfig, SUPPORTED_MODELS
from app.training.dataset_normalizer import DatasetNormalizer
from app.training.dataset_loader import DatasetLoader
from app.training.alpaca_formatter import AlpacaFormatter
from app.training.artifact_validator import ArtifactValidator

# These factories use lazy imports internally, so importing the class
# itself is safe even without torch/transformers/peft/trl installed.
from app.training.qlora_config import QLoRAConfigFactory
from app.training.peft_config import PEFTConfigFactory
from app.training.training_args import TrainingArgumentsFactory

__all__ = [
    "ModelConfig",
    "SUPPORTED_MODELS",
    "DatasetNormalizer",
    "DatasetLoader",
    "AlpacaFormatter",
    "QLoRAConfigFactory",
    "PEFTConfigFactory",
    "TrainingArgumentsFactory",
    "ArtifactValidator",
]
