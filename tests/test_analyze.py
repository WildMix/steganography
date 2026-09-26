"""Size-only analysis, copyable decimal rates and timed CLI regression tests."""
from fractions import Fraction
from io import StringIO
import json
import random
import re
import struct
import sys

import numpy as np
import pytest

from stegolab import system
from stegolab.cli import CommandProgress, main
from stegolab.system import Profile, decimal_rate, encode_png, minimum_gross_rate, plan_payload


@pytest.fixture
def inputs(tmp_path):
    paths = {name: tmp_path / name for name in ("cover.png", "message.bin", "key.bin")}
    pixels = np.random.default_rng(147).integers(10, 245, (512, 513), dtype=np.uint8)
    paths["cover.png"].write_bytes(encode_png(pixels))
    paths["message.bin"].write_bytes(b"HELLO")
    paths["key.bin"].write_bytes(bytes(range(32)))
    return paths


def arguments(inputs, action, rate, keyed=True):
    result = ["stegolab", action, str(inputs["cover.png"]), "--rate", rate]
    if action in ("analyze", "embed"):
        result += ["--message", str(inputs["message.bin"]), "--strategy", "balanced"]
    if keyed:
        result += ["--key", str(inputs["key.bin"])]
    return result


@pytest.mark.parametrize("keyed", [True, False])
@pytest.mark.parametrize("rate", ["0.05", "auto"])
@pytest.mark.parametrize("export_logs", [True, False])
def test_analyze_does_not_embed_encrypt_or_write(inputs, tmp_path, monkeypatch, capsys, keyed, rate, export_logs):
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    def forbidden(*args, **kwargs):
        pytest.fail("Analysis performed an embedding/cryptographic operation")
    for name in ("ChaCha20Poly1305", "compute_costs", "split_positions", "body_positions",
                 "columns", "root_key", "encode_png", "Stream"):
        monkeypatch.setattr(system, name, forbidden)
    monkeypatch.setattr(system.secrets, "token_bytes", forbidden)
    monkeypatch.setattr(system.coding, "embed", forbidden)
    log_report = tmp_path / "analysis.json"
    argv = arguments(inputs, "analyze", rate, keyed)
    if export_logs:
        argv += ["--output-logs", str(log_report)]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Walkthrough" not in captured.err
    assert "Size-only fit within supported profile: yes" in captured.err
    if export_logs:
        result = json.loads(log_report.read_text(encoding="utf-8"))
        assert result["status"] == "ok"
    else:
        assert not log_report.exists()
        result = system.analyze_configuration(inputs["cover.png"].read_bytes(),
            inputs["message.bin"].read_bytes(), inputs["key.bin"].read_bytes() if keyed else None,
            Profile(rate))
        result["fits_by_size"] = result["chosen"]["fits"] and result["chosen"]["supported"]
    assert result["fits_by_size"]
    assert result["chosen"]["salt_bytes"] == 32
    assert result["chosen"]["header_bytes"] == 18
    assert result["chosen"]["authentication_tag_bytes"] == (16 if keyed else 0)
    assert result["chosen"]["checksum_bytes"] == (0 if keyed else 4)
    assert ("Frame comparison" in captured.err) == (rate != "auto")
    for summary in (result["chosen"], result["suggested"]):
        assert summary["frame_bytes"] == sum(summary[field] for field in (
            "salt_bytes", "header_bytes", "stored_bytes", "padding_bytes",
            "authentication_tag_bytes", "checksum_bytes"))
        assert Profile(summary["chosen_rate"]).capacity(512 * 513) == summary["frame_bytes"]
        if export_logs:
            assert "/" not in summary["chosen_rate"]
    assert "Total elapsed time:" in captured.err
    assert "HELLO" not in captured.err + captured.out
    assert before == {p: p.read_bytes() for p in tmp_path.iterdir() if p != log_report}


@pytest.mark.parametrize("keyed", [True, False])
@pytest.mark.parametrize("message", [b"", b"HELLO", b"A" * 1000, bytes(range(256))])
def test_planner_components_and_compression(keyed, message):
    flag, stored, plan = plan_payload(message, 512 * 512, keyed, Profile("0.05"))
    assert stored == system.select_payload(message)[1]
    for summary in (plan["chosen"], plan["suggested"]):
        assert summary["compressed"] == bool(flag)
        assert summary["capacity_bytes"] == summary["frame_bytes"] - (66 if keyed else 54)
        assert summary["padding_bytes"] == summary["capacity_bytes"] - len(stored)
    if message == b"HELLO" and keyed:
        assert plan["chosen"]["frame_bytes"] == 1638
        assert plan["chosen"]["padding_bytes"] == 1567
        assert plan["suggested"]["frame_bytes"] == 81
        assert plan["suggested"]["padding_bytes"] == 10


@pytest.mark.parametrize("rate,count", [("0.0025", 300), ("auto", 7000), ("0.05", 7000)])
def test_analyze_reports_infeasible_size_without_embedding(inputs, monkeypatch, capsys, rate, count):
    inputs["message.bin"].write_bytes(random.Random(42).randbytes(count))
    log_report = inputs["cover.png"].parent / "infeasible.json"
    monkeypatch.setattr(sys, "argv", arguments(inputs, "analyze", rate) + ["--output-logs", str(log_report)])
    main()
    captured = capsys.readouterr()
    assert captured.out == ""
    report = json.loads(log_report.read_text(encoding="utf-8"))
    assert not report["fits_by_size"]
    assert "DOES NOT FIT" in captured.err or "UNSUPPORTED" in captured.err
    if rate != "auto":
        assert report["chosen"]["padding_bytes"] == 0
        assert report["chosen"]["deficit_bytes"] > 0
    assert report["suggested"]["supported"] == (count == 300)


@pytest.mark.parametrize("rate", ["0", "0.3", "invalid", "nan", "1/0"])
def test_analyze_invalid_rates_fail_cleanly(inputs, monkeypatch, capsys, rate):
    monkeypatch.setattr(sys, "argv", arguments(inputs, "analyze", rate))
    with pytest.raises(SystemExit) as error:
        main()
    captured = capsys.readouterr()
    assert error.value.code == 2
    assert "Traceback" not in captured.err
    assert "Total elapsed time:" in captured.err
    assert not captured.out


def test_analyze_rejects_invalid_key(inputs, monkeypatch, capsys):
    inputs["key.bin"].write_bytes(b"too short")
    monkeypatch.setattr(sys, "argv", arguments(inputs, "analyze", "auto"))
    with pytest.raises(SystemExit):
        main()
    assert "exactly 32" in capsys.readouterr().err


def test_report_cannot_overwrite_analysis_inputs(inputs, monkeypatch, capsys):
    original = inputs["message.bin"].read_bytes()
    monkeypatch.setattr(sys, "argv", arguments(inputs, "analyze", "auto")
                       + ["--output-logs", str(inputs["message.bin"])])
    with pytest.raises(SystemExit):
        main()
    assert inputs["message.bin"].read_bytes() == original
    assert "Log output already exists" in capsys.readouterr().err


def test_successful_default_embed_extract_have_only_readable_logs(inputs, tmp_path, monkeypatch, capsys):
    stego, recovered = tmp_path / "stego.png", tmp_path / "recovered.bin"
    original_paths = set(tmp_path.iterdir())
    monkeypatch.setattr(sys, "argv", arguments(inputs, "embed", "auto") + ["--output", str(stego)])
    main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Walkthrough" not in captured.err
    assert "Mode: keyed (encrypted)" in captured.err
    assert "Strategy: balanced; rate selection: automatic" in captured.err
    assert f"Output saved: {stego}" in captured.err
    rate = re.search(r"Chosen gross rate: ([0-9.]+) bpp", captured.err).group(1)
    args = arguments(inputs, "extract", rate)
    args[2] = str(stego)
    monkeypatch.setattr(sys, "argv", args + ["--output", str(recovered)])
    main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Walkthrough" not in captured.err
    assert f"Output saved: {recovered} (5 bytes)" in captured.err
    assert "Total elapsed time:" in captured.err
    assert recovered.read_bytes() == b"HELLO"
    assert set(tmp_path.iterdir()) == original_paths | {stego, recovered}


def test_decimal_rates_preserve_every_sampled_byte_budget():
    rng = random.Random(519)
    for pixels in (262144, 262656, 953600, 16777216):
        for keyed in (True, False):
            max_stored = Profile("0.2").capacity(pixels) - (66 if keyed else 54)
            for stored in (0, 5, max_stored, *[rng.randrange(max_stored + 1) for _ in range(250)]):
                exact = minimum_gross_rate(pixels, stored, keyed)
                decimal = decimal_rate(exact, pixels)
                assert re.fullmatch(r"0\.\d{8,}", decimal)
                assert Fraction(decimal) >= Fraction(exact)
                assert Profile(decimal).capacity(pixels) == Profile(exact).capacity(pixels)
        # Explicit rates immediately BELOW a byte boundary must not round across it.
        for total in (100, 1000, Profile("0.2").capacity(pixels)):
            exact = str(Fraction(total * 8, pixels) - Fraction(1, 10 ** 14))
            assert int(pixels * Fraction(decimal_rate(exact, pixels)) // 8) == total - 1
    assert decimal_rate("9163/119200", 953600) == "0.07687081"


@pytest.mark.parametrize("tty", [False, True])
def test_stage_timing_and_total_are_not_double_counted(tty):
    class Output(StringIO):
        def isatty(self):
            return tty
    output = Output()
    now = [0.0]
    progress = CommandProgress(output, clock=lambda: now[0])
    progress(0, "First stage")
    now[0] = 2.0
    progress(50, "Second stage")
    now[0] = 5.0
    progress.finish("Complete")
    assert [row["seconds"] for row in progress.timings] == [2.0, 3.0]
    assert progress.total_seconds == 5.0
    assert "[done: 2.000 s] First stage" in output.getvalue()
    assert "[done: 3.000 s] Second stage" in output.getvalue()
    assert "Total elapsed time: 5.000 s" in output.getvalue()


@pytest.mark.parametrize("keyed", [True, False])
def test_analyze_embed_extract_share_decimal_rate_and_timing(inputs, tmp_path, monkeypatch, capsys, keyed):
    inputs["message.bin"].write_bytes(bytes(range(20)))
    analyze_log, embed_log, extract_log = (tmp_path / name for name in ("analyze.json", "embed.json", "extract.json"))
    monkeypatch.setattr(sys, "argv", arguments(inputs, "analyze", "auto", keyed) + ["--output-logs", str(analyze_log)])
    main()
    assert capsys.readouterr().out == ""
    analysis = json.loads(analyze_log.read_text(encoding="utf-8"))
    stego, recovered = tmp_path / "stego.png", tmp_path / "recovered.bin"
    monkeypatch.setattr(sys, "argv", arguments(inputs, "embed", "auto", keyed)
                       + ["--output", str(stego), "--output-logs", str(embed_log)])
    main()
    assert capsys.readouterr().out == ""
    embedding = json.loads(embed_log.read_text(encoding="utf-8"))
    assert analysis["rate"] == embedding["rate"]
    args = arguments(inputs, "extract", embedding["rate"], keyed)
    args[2] = str(stego)
    monkeypatch.setattr(sys, "argv", args + ["--output", str(recovered), "--output-logs", str(extract_log)])
    main()
    captured = capsys.readouterr()
    assert recovered.read_bytes() == inputs["message.bin"].read_bytes()
    assert captured.out == ""
    assert "Walkthrough" not in captured.err
    report = json.loads(extract_log.read_text(encoding="utf-8"))
    assert all(row["status"] == "done" and row["seconds"] >= 0 for row in report["timings"])
    assert "100%  Extraction verified and saved" in captured.err
    for title in ("Reconstruct bootstrap positions", "Recover bootstrap syndrome",
                  "Derive body keys", "Recover body syndrome", "Validate header/lengths",
                  "Verify original length"):
        assert title in captured.err
    assert "Total elapsed time:" in captured.err


@pytest.mark.parametrize("rate", ["0.05", "auto"])
def test_planned_frame_matches_actual_aead_and_progress_preserves_pixels(monkeypatch, rate):
    cover = np.random.default_rng(612).integers(10, 245, (512, 512), dtype=np.uint8)
    message, key = b"HELLO", bytes(range(32))
    _, data, plan = plan_payload(message, cover.size, True, Profile(rate))
    expected = plan["chosen"]
    original_aead = system.ChaCha20Poly1305
    frames = []
    class RecordingAEAD:
        def __init__(self, key):
            self.aead = original_aead(key)
        def encrypt(self, nonce, frame, aad):
            frames.append((nonce, frame, aad))
            return self.aead.encrypt(nonce, frame, aad)
    monkeypatch.setattr(system, "ChaCha20Poly1305", RecordingAEAD)
    results = []
    for callback in (None, lambda *args: None):
        results.append(system.embed_pixels(cover, message, key, Profile(rate), strategy="balanced",
                                          progress=callback, random_bytes=random.Random(721).randbytes)[0])
    assert frames[0] == frames[1]
    assert frames[0][0] == bytes(12)
    frame = frames[0][1]
    assert struct.unpack(">BBQQ", frame[:18]) == (1, 0, len(message), len(data))
    assert frame[18:18 + len(data)] == data
    assert len(frame) - 18 - len(data) == expected["padding_bytes"]
    assert len(frame) + 32 + 16 == expected["frame_bytes"]
    assert encode_png(results[0]) == encode_png(results[1])
