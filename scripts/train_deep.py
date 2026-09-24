"""CPU-capable residual CNN. Independent detector, explicitly not a full SRNet reproduction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from sklearn.metrics import roc_auc_score, roc_curve

from stegolab.evaluation import metrics

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


class ResidualBlock(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.layers = nn.Sequential(nn.Conv2d(width, width, 3, padding=1, bias=False),
                                    nn.BatchNorm2d(width), nn.ReLU(),
                                    nn.Conv2d(width, width, 3, padding=1, bias=False), nn.BatchNorm2d(width))
        self.relu = nn.ReLU()

    def forward(self, x):
        return self.relu(x + self.layers(x))


class ResidualDetector(nn.Module):
    def __init__(self):
        super().__init__()
        kernels = [
            [[0,0,0],[0,-1,1],[0,0,0]], [[0,0,0],[0,-1,0],[0,1,0]],
            [[0,0,0],[1,-2,1],[0,0,0]], [[0,1,0],[0,-2,0],[0,1,0]],
            [[0,1,0],[1,-4,1],[0,1,0]], [[-1,2,-1],[2,-4,2],[-1,2,-1]],
            [[-1,0,0],[0,1,0],[0,0,0]], [[0,0,-1],[0,1,0],[0,0,0]],
        ]
        filters = torch.tensor(kernels, dtype=torch.float32)[:, None]
        filters /= filters.square().sum((1,2,3), keepdim=True).sqrt()
        self.register_buffer("filters", filters)
        self.front = nn.Sequential(nn.Conv2d(8, 8, 3, padding=1, bias=False), nn.BatchNorm2d(8),
                                    nn.ReLU(), ResidualBlock(8), nn.AvgPool2d(4))
        self.middle = nn.Sequential(nn.Conv2d(8, 16, 3, padding=1, bias=False), nn.BatchNorm2d(16),
                                     nn.ReLU(), ResidualBlock(16), nn.AvgPool2d(2),
                                     nn.Conv2d(16, 32, 3, padding=1, bias=False), nn.BatchNorm2d(32),
                                     nn.ReLU(), ResidualBlock(32))
        self.classifier = nn.Linear(64, 1)

    def forward(self, x):
        residual = nn.functional.conv2d(x, self.filters, padding=1).clamp(-3, 3)
        features = self.middle(self.front(residual))
        stats = torch.cat([features.mean((2,3)), features.square().mean((2,3))], 1)
        return self.classifier(stats).squeeze(1)


class Pairs(Dataset):
    def __init__(self, identifiers, variant, training, cache=True):
        self.identifiers, self.variant, self.training = identifiers, variant, training
        self.accepted = []
        self.samples = [] if cache else None
        for identifier in identifiers:
            folder = ARTIFACTS / "samples" / identifier
            if (folder / f"{variant}.npy").exists():
                self.accepted.append(identifier)
            else:
                record_path = folder / f"{variant.rsplit('_', 1)[-1]}.json"
                record = json.loads(record_path.read_text()) if record_path.exists() else {}
                if "failure" not in record:
                    raise ValueError(f"Incomplete data: {identifier}/{variant}")
            if cache:
                self.samples.append(self.read_pair(identifier))

    def read_pair(self, identifier):
        folder = ARTIFACTS / "samples" / identifier
        cover = np.load(folder / "cover.npy")
        candidate = folder / f"{self.variant}.npy"
        valid = candidate.exists()
        stego = np.load(candidate) if valid else cover
        return np.stack([cover, stego]), valid

    def __len__(self):
        return len(self.identifiers)

    def __getitem__(self, index):
        pair, valid = self.samples[index] if self.samples is not None else self.read_pair(self.identifiers[index])
        if self.training:
            row, col = np.random.randint(0, 385, size=2)
            pair = pair[:, row:row+128, col:col+128]
            pair = np.rot90(pair, np.random.randint(4), axes=(1,2))
            if np.random.rand() < .5:
                pair = pair[:, :, ::-1]
        return torch.from_numpy(np.ascontiguousarray(pair)).float().unsqueeze(1), valid


def infer(model, loader, device):
    model.eval()
    covers, stegos = [], []
    with torch.inference_mode():
        for pairs, valid in loader:
            batch = len(pairs)
            pixels = pairs.flatten(0,1).to(device)
            # Four 256x256 non-overlapping quadrants cover the complete image.
            scores = []
            for row, col in ((0,0), (0,256), (256,0), (256,256)):
                scores.append(model(pixels[:, :, row:row+256, col:col+256]))
            values = torch.stack(scores).mean(0).reshape(batch, 2).cpu().numpy()
            covers.extend(values[:, 0]); stegos.extend(values[valid.numpy(), 1])
    return np.array(covers), np.array(stegos)


def atomic_json(path, record):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-pairs", type=int, default=16)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--seed", type=int, default=3187)
    parser.add_argument("--validate-every", type=int, default=3)
    parser.add_argument("--init", type=Path)
    parser.add_argument("--no-cache", action="store_true", help="Reload rasters per epoch instead of using about 0.8 GiB")
    parser.add_argument("--save-validation-checkpoints", action="store_true",
                        help="Retain each validation-epoch state for exact transfer-initialization replay")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text())
    folder = ARTIFACTS / "deep" / args.variant
    folder.mkdir(parents=True, exist_ok=True)
    model = ResidualDetector().to(device)
    if args.init and not args.final:
        model.load_state_dict(torch.load(args.init, map_location=device, weights_only=True))
    def loader(part, training=False):
        return DataLoader(Pairs(manifest["parts"][part], args.variant, training, cache=not args.no_cache),
                          batch_size=args.batch_pairs if training else 8, shuffle=training, num_workers=0)
    def groups(part, accepted):
        return ([manifest["group_ids"][i] for i in manifest["parts"][part]],
                [manifest["group_ids"][i] for i in accepted])
    if args.final:
        state = torch.load(folder / "best.pt", map_location=device, weights_only=True)
        model.load_state_dict(state)
        calibration = json.loads((folder / "validation.json").read_text())
        test_loader = loader("test")
        c, s = infer(model, test_loader, device)
        c *= calibration["direction"]; s *= calibration["direction"]
        result = metrics(c, s, calibration["threshold"], calibration["low_fpr_threshold"],
                         groups=groups("test", test_loader.dataset.accepted))
        accepted = set(test_loader.dataset.accepted)
        selected = np.array([i for i, identifier in enumerate(manifest["parts"]["test"])
                             if identifier in accepted])
        accepted_groups = [manifest["group_ids"][i] for i in test_loader.dataset.accepted]
        result["test_conditional_on_acceptance"] = metrics(
            c[selected], s, calibration["threshold"], calibration["low_fpr_threshold"],
            groups=(accepted_groups, accepted_groups))
        result["test_rejections"] = [i for i in manifest["parts"]["test"] if i not in accepted]
        result.update({"variant": args.variant, "architecture": "compact residual CNN", "seed": args.seed,
                       "training_epochs": calibration["selected_epoch"], "device": str(device)})
        np.savez(folder / "test_predictions.npz", cover=c, stego=s,
                 cover_ids=np.array(manifest["parts"]["test"]), stego_ids=np.array(test_loader.dataset.accepted))
        atomic_json(folder / "final.json", result)
        if args.variant == "balanced_auto":
            from report_results import main as report_results
            report_results()
        print(json.dumps(result, indent=2), flush=True)
        return
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    best, history = 0, []
    train = loader("train", True)
    validation = loader("validation")
    for epoch in range(1, args.epochs + 1):
        started, total_loss = time.perf_counter(), 0.0
        model.train()
        for pairs, valid in train:
            pixels = pairs.flatten(0,1).to(device)
            labels = torch.tensor([0., 1.], device=device).repeat(len(pairs))
            keep = (labels == 0) | valid.to(device).repeat_interleave(2)
            pixels, labels = pixels[keep], labels[keep]
            optimizer.zero_grad(set_to_none=True)
            logits = model(pixels)
            loss = nn.functional.binary_cross_entropy_with_logits(logits, labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(pairs)
        scheduler.step()
        if epoch % args.validate_every and epoch != args.epochs:
            record = {"epoch": epoch, "loss": total_loss / len(train.dataset),
                      "seconds": time.perf_counter() - started}
            history.append(record)
            print(json.dumps(record), flush=True)
            atomic_json(folder / "history.json", history)
            if args.variant == "balanced_auto":
                from report_results import main as report_results
                report_results()
            continue
        c, s = infer(model, validation, device)
        y = np.r_[np.zeros(len(c), dtype=int), np.ones(len(s), dtype=int)]
        raw = np.r_[c, s]
        auc = float(roc_auc_score(y, raw))
        record = {"epoch": epoch, "loss": total_loss / len(train.dataset), "auc": auc,
                  "seconds": time.perf_counter() - started}
        history.append(record)
        print(json.dumps(record), flush=True)
        oriented = max(auc, 1-auc)
        if args.save_validation_checkpoints:
            torch.save(model.state_dict(), folder / f"epoch_{epoch:03d}.pt")
        if oriented > best:
            best = oriented
            direction = 1 if auc >= .5 else -1
            scores = raw * direction
            fpr, tpr, thresholds = roc_curve(y, scores)
            finite = np.flatnonzero(np.isfinite(thresholds))
            threshold = float(thresholds[finite[np.argmin((fpr + 1-tpr)[finite])]])
            low_threshold = float(np.quantile(scores[:len(c)], .99, method="higher"))
            calibration = {"variant": args.variant, "architecture": "compact residual CNN",
                           "parameters": sum(p.numel() for p in model.parameters()),
                           "seed": args.seed, "selected_epoch": epoch, "direction": direction,
                           "initialization": str(args.init) if args.init else "random",
                           "threshold": threshold, "low_fpr_threshold": low_threshold,
                           "validation": metrics(scores[:len(c)], scores[len(c):], threshold, low_threshold,
                                                 groups=groups("validation", validation.dataset.accepted))}
            torch.save(model.state_dict(), folder / "best.pt")
            atomic_json(folder / "validation.json", calibration)
        atomic_json(folder / "history.json", history)
        if args.variant == "balanced_auto":
            from report_results import main as report_results
            report_results()


if __name__ == "__main__":
    main()
