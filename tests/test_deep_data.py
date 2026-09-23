from pathlib import Path

import numpy as np
import pytest


def test_cached_neural_pairs_preserve_pixels_and_augmentation(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import train_deep
    monkeypatch.setattr(train_deep, "ARTIFACTS", tmp_path)
    folder = tmp_path / "samples" / "sample"
    folder.mkdir(parents=True)
    cover = np.random.default_rng(731).integers(0, 256, (512, 512), dtype=np.uint8)
    stego = cover ^ 1
    np.save(folder / "cover.npy", cover)
    np.save(folder / "control.npy", stego)
    cached = train_deep.Pairs(["sample"], "control", True, cache=True)
    streamed = train_deep.Pairs(["sample"], "control", True, cache=False)
    for seed in range(4):
        np.random.seed(seed)
        a, valid_a = cached[0]
        np.random.seed(seed)
        b, valid_b = streamed[0]
        assert torch.equal(a, b)
        assert valid_a and valid_b
        assert tuple(a.shape) == (2, 1, 128, 128)
    np.testing.assert_array_equal(cached.samples[0][0][0], cover)
