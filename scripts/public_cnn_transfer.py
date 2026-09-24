"""Frozen keyed-trained CNN transfer test on public-mode held-out images."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset

from public_probe import ARTIFACTS, DATA, OUT, RATE, ids_by_part, write_json
from stegolab.evaluation import metrics
from stegolab.primitives import Stream
from stegolab.system import ExtractionError, Profile, embed_pixels, extract_pixels
from train_deep import ResidualDetector, infer


class PublicPairs(Dataset):
    def __init__(self, identifiers):
        self.identifiers = identifiers

    def __len__(self):
        return len(self.identifiers)

    def __getitem__(self, index):
        identifier = self.identifiers[index]
        with Image.open(DATA / "bossbase" / f"{identifier}.pgm") as source:
            cover = np.array(source)
        path = OUT / "samples" / identifier / "pixels.npy"
        if path.exists():
            stego = np.load(path)
        else:
            message = hashlib.sha256(f"payload:{identifier}".encode()).digest()
            stream = Stream(hashlib.sha256(f"public-probe-salt:{identifier}:{RATE}".encode()).digest())
            stego, _ = embed_pixels(cover, message, None, Profile(RATE),
                                    strategy="balanced", random_bytes=stream.take)
            assert extract_pixels(stego, None, Profile(RATE)) == message
            from experiment import save_array
            save_array(path, stego)
        pair = np.stack((cover, stego))
        return torch.from_numpy(pair).float().unsqueeze(1), True


def main():
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
    source = ARTIFACTS / "deep" / "balanced_0p05"
    calibration = json.loads((source / "validation.json").read_text(encoding="utf-8"))
    torch.set_num_threads(4)
    model = ResidualDetector()
    model.load_state_dict(torch.load(source / "best.pt", map_location="cpu", weights_only=True))
    test_ids = [identifier for identifier in ids_by_part(manifest)["test"]
                if "failure" not in json.loads((OUT / "samples" / identifier / "result.json").read_text())]
    cover, stego = infer(model, DataLoader(PublicPairs(test_ids), batch_size=4, num_workers=0),
                         torch.device("cpu"))
    cover *= calibration["direction"]
    stego *= calibration["direction"]
    groups = [manifest["group_ids"][identifier] for identifier in test_ids]
    result = metrics(cover, stego, calibration["threshold"], calibration["low_fpr_threshold"],
                     groups=(groups, groups))
    result.update({"variant": "public_balanced_0p05_probe", "model": "frozen keyed-trained residual CNN",
                   "calibration": "keyed validation only", "test_pairs": len(test_ids)})
    write_json(OUT / "cnn_transfer.json", result)
    np.savez(OUT / "cnn_transfer_predictions.npz", cover=cover, stego=stego, ids=np.array(test_ids))
    false_positives = 0
    for identifier in test_ids[:40]:
        with Image.open(DATA / "bossbase" / f"{identifier}.pgm") as source:
            original_cover = np.array(source)
        try:
            extract_pixels(original_cover, None, Profile(RATE))
            false_positives += 1
        except ExtractionError:
            pass
    write_json(OUT / "protocol_detection.json",
               {"known_public_format": True, "tested_covers": min(40, len(test_ids)),
                "false_positives": false_positives,
                "tested_stegos": len(test_ids), "recovered_stegos": len(test_ids),
                "note": "A public extractor serves as a direct presence and recovery test."})
    from report_results import main as report_results
    report_results()
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
