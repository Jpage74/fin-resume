"""Embedding 封装：可插拔。

默认 fastembed 加载 BAAI/bge-small-zh-v1.5（中文检索，ONNX 轻量、无需 torch）。
模型本地缓存，首次使用自动下载；网络受限时可设 HF_ENDPOINT=https://hf-mirror.com 走镜像。

懒加载：import 不触发下载，加载失败自动降级为不可用，由调用方走关键词兜底，
保证管线不因模型缺失而断。
"""
from __future__ import annotations


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None

    def _ensure(self):
        if self._model is None:
            import os

            # 国内网络默认走 hf-mirror 镜像；禁用 xet 协议（hf-mirror 不支持，会 401）
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        m = self._ensure()
        # 统一转 float32 numpy 数组：Chroma 不接受「Python 列表包 numpy 标量」
        return np.asarray([list(v) for v in m.embed(list(texts))], dtype=np.float32)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    @property
    def available(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:
            return False
