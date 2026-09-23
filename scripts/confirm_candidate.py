"""Freeze a validation-selected candidate, train its CNN, and confirm on untouched test data.

Only invoke after reviewing development comparisons. Fail closed on incomplete or
failed validation gates. Generated-but-unscored test samples are not selection evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time
from datetime import datetime, timezone

from experiment import ARTIFACTS, ROOT, write_json


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(script, *arguments, log_name):
    log = ARTIFACTS / log_name
    print(f"Starting {script} {' '.join(arguments)}; log={log.name}", flush=True)
    with log.open("w", encoding="utf-8") as output:
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments],
                       cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()
    variant = args.variant
    strategy, tag = variant.rsplit("_", 1)
    if strategy not in ("baseline", "balanced") or tag not in ("0p05", "0p025", "0p01", "0p005"):
        parser.error("Specify an existing, predeclared candidate variant")
    selected_path = ARTIFACTS / "selection.json"
    if selected_path.exists():
        parser.error("A selection record already exists; review it rather than silently replacing it")
    record = read(ARTIFACTS / "models" / variant / "validation.json")
    if not all(item["validation"]["passes_provisional_upper_bound"] for item in record["detectors"].values()):
        parser.error("The candidate has not passed every classical validation bound")
    control = read(ARTIFACTS / "models" / "control" / "validation.json")
    for name in ("residual_subspace_ensemble", "residual_extra_trees"):
        if control["detectors"][name]["validation"]["auc_95_interval"][0] <= .75:
            parser.error(f"The {name} positive control has insufficient validation sensitivity")
    variants = sorted({variant, "baseline_0p05", "control"})
    frozen = {name: digest(ARTIFACTS / "models" / name / "models.joblib") for name in variants}
    selection = {"variant": variant, "selected_utc": datetime.now(timezone.utc).isoformat(),
                 "scope": "Classical validation selected; neural validation must also pass before test scoring",
                 "comparators": ["baseline_0p05", "control"], "classical_model_sha256": frozen,
                 "validation": record, "final_test_scored": False}
    write_json(selected_path, selection)
    # Start the expensive sample generation while independent neural fitting runs.
    generators = []
    rates = sorted({tag, "0p05"})
    workers = "8" if len(rates) == 1 else "4"
    for rate_tag in rates:
        log = (ARTIFACTS / f"generate_test_{rate_tag}.log").open("w", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "experiment.py"), "generate",
                                    "--part", "test", "--rate", rate_tag.replace("p", "."), "--workers", workers],
                                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        generators.append((process, log))
    try:
        while True:
            history_path = ARTIFACTS / "deep" / "control" / "history.json"
            calibration_path = ARTIFACTS / "deep" / "control" / "validation.json"
            if calibration_path.exists():
                control_calibration = read(calibration_path)
                if control_calibration["validation"]["auc_95_interval"][0] > .75:
                    break
                if history_path.exists() and read(history_path)[-1]["epoch"] == 9:
                    raise RuntimeError("Neural control sensitivity is inadequate; final scores remain unopened")
            print("Waiting for a sufficiently sensitive neural positive-control checkpoint", flush=True)
            time.sleep(30)
        seed_folder = ARTIFACTS / "deep" / variant
        seed_folder.mkdir(parents=True, exist_ok=True)
        seed_path = seed_folder / "control_initialization.pt"
        shutil.copyfile(ARTIFACTS / "deep" / "control" / "best.pt", seed_path)
        selection["neural_initialization"] = {"control_calibration": control_calibration,
                                               "checkpoint_sha256": digest(seed_path)}
        write_json(selected_path, selection)
        invoke("train_deep.py", "--variant", variant, "--epochs", "15", "--threads", "4",
               "--validate-every", "3", "--init", str(seed_path),
               log_name=f"train_deep_{variant}.log")
        neural = read(ARTIFACTS / "deep" / variant / "validation.json")
        selection["neural_validation"] = neural
        selection["neural_model_sha256"] = digest(ARTIFACTS / "deep" / variant / "best.pt")
        write_json(selected_path, selection)
        if not neural["validation"]["passes_provisional_upper_bound"]:
            raise RuntimeError("Neural validation failed the provisional target; final scores remain unopened")
    finally:
        for process, log in generators:
            status = process.wait()
            log.close()
            if status:
                raise RuntimeError(f"Test generation failed with exit {status}; inspect its log")
    for name in variants:
        if digest(ARTIFACTS / "models" / name / "models.joblib") != frozen[name]:
            raise RuntimeError("A supposedly frozen detector changed")
    while read(ARTIFACTS / "deep" / "control" / "history.json")[-1]["epoch"] != 9:
        print("Waiting for the full control run before freezing its final checkpoint", flush=True)
        time.sleep(30)
    selection["neural_control_sha256"] = digest(ARTIFACTS / "deep" / "control" / "best.pt")
    selection["scope"] = "Classical and neural validation gates passed; independent confirmation underway"
    selection["final_test_scored"] = True
    write_json(selected_path, selection)
    for name in variants:
        invoke("experiment.py", "evaluate", "--variant", name, "--final", log_name=f"final_{name}.log")
    for name in (variant, "control"):
        invoke("train_deep.py", "--variant", name, "--final", "--threads", "4", log_name=f"deep_final_{name}.log")
    invoke("report_results.py", log_name="report_results.log")
    invoke("record_environment.py", log_name="record_environment.log")
    final = read(ARTIFACTS / "models" / variant / "final.json")
    neural_final = read(ARTIFACTS / "deep" / variant / "final.json")
    passed = all(item["test"]["passes_provisional_upper_bound"] for item in final["detectors"].values())
    passed = passed and neural_final["passes_provisional_upper_bound"]
    selection["confirmation_complete"] = True
    selection["candidate_bounds_pass"] = passed
    write_json(selected_path, selection)
    print(json.dumps({"variant": variant, "candidate_bounds_pass": passed,
                      "note": "Review held-out positive controls and stated limitations before drawing a conclusion"}), flush=True)


if __name__ == "__main__":
    main()
