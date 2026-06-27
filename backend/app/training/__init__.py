"""QLoRA training engine.

Heavy ML dependencies (torch, transformers, peft, trl) are imported
lazily inside factory methods, so the package can be imported without
those packages installed (e.g. in test environments).
"""

from app.training.model_registry import ModelConfig, SUPPORTED_MODELS
from app.training.dataset_loader import DatasetLoader
from app.training.alpaca_formatter import AlpacaFormatter
from app.training.artifact_validator import ArtifactValidator
from app.training.training_args import TrainingArgumentsFactory

__all__ = [
    "ModelConfig",
    "SUPPORTED_MODELS",
    "DatasetLoader",
    "AlpacaFormatter",
    "TrainingArgumentsFactory",
    "ArtifactValidator",
]
