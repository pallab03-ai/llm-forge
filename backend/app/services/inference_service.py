"""Inference service: loads a base model + LoRA adapter and reuses it.

Heavy ML imports are lazy so the module loads cleanly in tests. A
production backend (vLLM/TGI/Triton) can replace this class without
changing the API contract.
"""

from __future__ import annotations

import os


class InferenceError(Exception):
    code = "INFERENCE_ERROR"
    http_status = 400


class InferenceService:
    def __init__(self) -> None:
        self._key: str | None = None
        self._tokenizer = None
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _cache_key(self, artifact_path: str, base_model: str) -> str:
        return f"{base_model}:{artifact_path}"

    def load(self, artifact_path: str, base_model: str) -> None:
        key = self._cache_key(artifact_path, base_model)
        if self._key == key:
            return

        if not os.path.isdir(artifact_path):
            raise InferenceError(
                f"Adapter artifact not found at path: {artifact_path}"
            )

        self.unload()

        import torch
        from peft import PeftModel
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        # Tokenizer lives in adapter_path/tokenizer/ (QLoRA training layout).
        tokenizer_path = os.path.join(artifact_path, "tokenizer")
        if os.path.isdir(tokenizer_path):
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
        else:
            tokenizer = AutoTokenizer.from_pretrained(artifact_path)

        # 4-bit NF4 quantization must match the training-time config
        # — otherwise the LoRA weights decode against the wrong base.
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(base, artifact_path)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        self._key = key

    def generate(
        self,
        prompt: str,
        *,
        max_new_tokens: int = 1024,
        temperature: float = 0.7,
        do_sample: bool = True,
    ) -> str:
        if not self.is_loaded:
            raise InferenceError("No model is loaded")

        import torch

        inputs_enc = self._tokenizer(prompt, return_tensors="pt")
        inputs_enc = {
            k: v.to(self._model.device) for k, v in inputs_enc.items()
        }
        input_len = inputs_enc["input_ids"].shape[-1]

        with torch.no_grad():
            out = self._model.generate(
                **inputs_enc,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=do_sample,
            )

        # Return only the newly generated tokens, not the prompt.
        return self._tokenizer.decode(
            out[0][input_len:], skip_special_tokens=True
        )

    def unload(self) -> None:
        self._key = None
        self._tokenizer = None
        self._model = None
