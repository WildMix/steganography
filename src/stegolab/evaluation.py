"""Paired, image-grouped evaluation. Model choice and score direction use validation only."""
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import roc_auc_score, roc_curve


class AdjacentBinStatistic:
    """Classical adjacent-intensity-bin statistic; no fitted image features."""
    def fit(self, x, y):
        return self

    def decision_function(self, x):
        # Tail layout: histogram[256], pair differences[128], RS[18], PNG size[1].
        histogram = x[:, -403:-147].astype(float)
        even, odd = histogram[:, ::2], histogram[:, 1::2]
        return -np.sum((even - odd) ** 2 / np.maximum(even + odd, 1e-12), axis=1)


class RegularityStatistic:
    """RS-like regular/singular group imbalance, not an LSB-rate estimator."""
    def fit(self, x, y):
        return self

    def decision_function(self, x):
        rs = x[:, -19:-1].reshape(len(x), 6, 3)
        return -np.mean(rs[:, :, 0] - rs[:, :, 1], axis=1)


class SubspaceEnsemble:
    def __init__(self, seed=551, learners=64, dimension=192, shrinkage=0.2):
        self.seed, self.learners, self.dimension, self.shrinkage = seed, learners, dimension, shrinkage

    def fit(self, x, y):
        rng = np.random.default_rng(self.seed)
        self.mean = np.mean(x, axis=0)
        self.scale = np.maximum(np.std(x, axis=0), 1e-6)
        valid = np.flatnonzero(np.std(x, axis=0) > 1e-7)
        self.models = []
        for _ in range(self.learners):
            selected = rng.choice(valid, min(self.dimension, len(valid)), replace=False)
            data = (x[:, selected].astype(float) - self.mean[selected]) / self.scale[selected]
            mean0, mean1 = data[y == 0].mean(axis=0), data[y == 1].mean(axis=0)
            centered = data - np.where(y[:, None] == 0, mean0, mean1)
            covariance = centered.T @ centered / max(1, len(data) - 2)
            regularized = ((1 - self.shrinkage) * covariance
                           + self.shrinkage * np.diag(np.maximum(np.diag(covariance), 0.01))
                           + np.eye(len(selected)) * 1e-5)
            weight = np.linalg.solve(regularized, mean1 - mean0)
            offset = (mean0 + mean1) @ weight / 2
            scale = max(float(np.std(data @ weight)), 1e-8)
            self.models.append((selected, weight, offset, scale))
        return self

    def decision_function(self, x):
        score = np.zeros(len(x))
        for selected, weight, offset, scale in self.models:
            data = (x[:, selected].astype(float) - self.mean[selected]) / self.scale[selected]
            score += (data @ weight - offset) / scale
        return score / len(self.models)


def dataset(cover, stego):
    return np.concatenate([cover, stego]), np.r_[np.zeros(len(cover), dtype=int), np.ones(len(stego), dtype=int)]


def auc_interval(cover_scores, stego_scores, seed=735, repetitions=1000, groups=None):
    # Resample independent image units and keep both labels of each unit together.
    rng = np.random.default_rng(seed)
    nc, ns = len(cover_scores), len(stego_scores)
    if groups is None:
        group_c, group_s = np.arange(nc), np.arange(ns)
    elif isinstance(groups, tuple):
        group_c, group_s = map(np.asarray, groups)
    else:
        group_c = group_s = np.asarray(groups)
    labels = np.r_[np.zeros(nc, dtype=int), np.ones(ns, dtype=int)]
    scores = np.r_[cover_scores, stego_scores]
    group_all = np.r_[group_c, group_s]
    units = [np.flatnonzero(group_all == group) for group in np.unique(group_all)]
    estimates = []
    for _ in range(repetitions):
        draw = np.concatenate([units[i] for i in rng.integers(0, len(units), len(units))])
        if len(np.unique(labels[draw])) == 2:
            estimates.append(roc_auc_score(labels[draw], scores[draw]))
    return np.quantile(estimates, [0.025, 0.975]).tolist()


def metrics(cover_scores, stego_scores, threshold, low_fpr_threshold, groups=None):
    y = np.r_[np.zeros(len(cover_scores), dtype=int), np.ones(len(stego_scores), dtype=int)]
    scores = np.r_[cover_scores, stego_scores]
    interval = auc_interval(cover_scores, stego_scores, groups=groups)
    auc = float(roc_auc_score(y, scores))
    robust_upper = max(interval[1], 1.0 - interval[0])
    return {"cover_images": len(cover_scores), "stego_images": len(stego_scores),
            "auc": auc, "orientation_robust_auc": max(auc, 1.0 - auc),
            "auc_95_interval": interval,
            "orientation_robust_auc_upper_95": robust_upper,
            "equal_prior_error": float((np.mean(cover_scores >= threshold)
                                        + np.mean(stego_scores < threshold)) / 2),
            "false_positive_rate": float(np.mean(cover_scores >= threshold)),
            "true_positive_rate_at_validation_1pct_fpr": float(np.mean(stego_scores >= low_fpr_threshold)),
            "actual_false_positive_rate_at_that_threshold": float(np.mean(cover_scores >= low_fpr_threshold)),
            "passes_provisional_upper_bound": robust_upper <= 0.55}


def fit_detectors(train_cover, train_stego, val_cover, val_stego, groups=None):
    train_x, train_y = dataset(train_cover, train_stego)
    val_x, val_y = dataset(val_cover, val_stego)
    models = {
        "adjacent_bin_chisquare": AdjacentBinStatistic(),
        "rs_like_regularity": RegularityStatistic(),
        "residual_subspace_ensemble": SubspaceEnsemble(),
        "residual_extra_trees": ExtraTreesClassifier(n_estimators=200, min_samples_leaf=4,
                                                       max_features="sqrt", n_jobs=4, random_state=831,
                                                       class_weight="balanced"),
    }
    results = {}
    for name, model in models.items():
        model.fit(train_x, train_y)
        if hasattr(model, "decision_function"):
            raw = model.decision_function(val_x)
        else:
            raw = model.predict_proba(val_x)[:, 1]
        direction = 1 if roc_auc_score(val_y, raw) >= .5 else -1
        score = raw * direction
        fpr, tpr, thresholds = roc_curve(val_y, score)
        finite = np.flatnonzero(np.isfinite(thresholds))
        threshold = float(thresholds[finite[np.argmin((fpr + 1 - tpr)[finite])]])
        low_threshold = float(np.quantile(score[:len(val_cover)], .99, method="higher"))
        results[name] = {"model": model, "direction": direction, "threshold": threshold,
                         "low_fpr_threshold": low_threshold,
                         "validation": metrics(score[:len(val_cover)], score[len(val_cover):], threshold, low_threshold,
                                               groups=groups)}
    return results


def predict(model_record, cover, stego):
    x, _ = dataset(cover, stego)
    model = model_record["model"]
    raw = model.decision_function(x) if hasattr(model, "decision_function") else model.predict_proba(x)[:, 1]
    raw = raw * model_record["direction"]
    return raw[:len(cover)], raw[len(cover):]
