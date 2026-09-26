import sys
import json

import numpy as np
import pytest

from stegolab.cli import main
from stegolab.system import (ExtractionError, Profile, encode_png, extract_and_decrypt,
                             minimum_gross_rate, prepare_payload)


def test_keygen_refuses_overwrite(tmp_path, monkeypatch, capsys):
    path = tmp_path / "key.bin"
    monkeypatch.setattr(sys, "argv", ["stegolab", "keygen", str(path)])
    main()
    original = path.read_bytes()
    assert len(original) == 32
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"Output saved: {path} (32 bytes)" in captured.err
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert path.read_bytes() == original


def test_failed_extraction_has_no_output(tmp_path, monkeypatch, capsys):
    image, key, output = (tmp_path / name for name in ("bad.png", "key.bin", "message.bin"))
    image.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    key.write_bytes(bytes(32))
    log_report = tmp_path / "failure.json"
    monkeypatch.setattr(sys, "argv", ["stegolab", "extract", str(image), "--key", str(key),
                                     "--output", str(output), "--output-logs", str(log_report)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    stderr = captured.err
    assert "No valid authenticated payload" in stderr
    assert "Traceback" not in stderr
    report = json.loads(log_report.read_text(encoding="utf-8"))
    assert report["status"] == "error"
    assert report["error"] == "No valid authenticated payload"
    assert report["timings"][-1]["status"] == "failed"


def test_malformed_images_share_generic_failure():
    for data in (b"", b"not png", b"\x89PNG\r\n\x1a\ntruncated"):
        with pytest.raises(ExtractionError, match="^No valid authenticated payload$") as error:
            extract_and_decrypt(data, bytes(32))
        assert error.value.__suppress_context__


def test_keyed_embed_reports_capacity_and_progress(tmp_path, monkeypatch, capsys):
    image, message, key, output = (tmp_path / name for name in
                                   ("cover.png", "message.bin", "key.bin", "stego.png"))
    image.write_bytes(encode_png(np.random.default_rng(123).integers(10, 245, (512, 512), dtype=np.uint8)))
    message.write_bytes(bytes(range(20)))
    key.write_bytes(bytes(range(32)))
    log_report = tmp_path / "embedding.json"
    monkeypatch.setattr(sys, "argv", ["stegolab", "embed", str(image), "--message", str(message),
                                     "--key", str(key), "--output", str(output), "--rate", "0.01",
                                     "--output-logs", str(log_report)])
    main()
    captured = capsys.readouterr()
    assert "Net bpp: 0.00061035 original" in captured.err
    assert "Gross bpp: 0.00997925" in captured.err
    assert "Capacity used: 7.66% (20 / 261 stored bytes)" in captured.err
    assert "Suggested minimum gross rate: 0.00262452 bpp" in captured.err
    assert "Chosen gross rate: 0.01000000 bpp" in captured.err
    assert "Computing adaptive costs" in captured.err
    assert "Embedding payload body" in captured.err
    assert "100%  Embedding verified" in captured.err
    assert "Total elapsed time:" in captured.err
    assert captured.out == ""
    assert "Walkthrough" not in captured.err
    report = json.loads(log_report.read_text(encoding="utf-8"))
    assert report["chosen"]["stored_bytes"] == 20
    assert report["status"] == "ok"
    assert all(row["seconds"] >= 0 and row["status"] == "done" for row in report["timings"])
    assert sum(row["seconds"] for row in report["timings"]) <= report["seconds"]
    for title in ("Pack 18-byte header", "Generate 32-byte random salt", "ChaCha20-Poly1305 encryption",
                  "XOR body", "Computing adaptive costs", "Embedding payload body",
                  "Apply +/-1", "Decode saved PNG"):
        assert title in captured.err
    assert extract_and_decrypt(output.read_bytes(), key.read_bytes(), Profile("0.01")) == message.read_bytes()


def test_oversized_payload_is_reported_before_cost_map(tmp_path, monkeypatch, capsys):
    from stegolab import system
    image, message, key, output = (tmp_path / name for name in
                                   ("cover.png", "message.bin", "key.bin", "stego.png"))
    image.write_bytes(encode_png(np.random.default_rng(124).integers(10, 245, (512, 512), dtype=np.uint8)))
    message.write_bytes(np.random.default_rng(125).bytes(300))
    key.write_bytes(bytes(range(32)))
    monkeypatch.setattr(system, "compute_costs", lambda _: pytest.fail("cost map computed for oversized payload"))
    monkeypatch.setattr(sys, "argv", ["stegolab", "embed", str(image), "--message", str(message),
                                     "--key", str(key), "--output", str(output), "--rate", "0.01"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "Capacity used: 114.94% (300 / 261 stored bytes)" in captured.err
    assert "Chosen gross rate: 0.01000000 bpp" in captured.err
    assert "Payload requires 300 bytes; capacity is 261" in captured.err
    assert not output.exists()
    assert "[failed:" in captured.err
    assert "Total elapsed time:" in captured.err
    assert "100%" not in captured.err


def test_preflight_uses_stored_length_after_compression():
    pixels = 512 * 512
    total = Profile("0.01").capacity(pixels)
    flag, stored, summary = prepare_payload(b"A" * 1000, total, pixels, True)
    assert flag == 1
    assert len(stored) < summary["capacity_bytes"] == 261
    assert summary["net_bpp"] > summary["gross_bpp"]
    assert summary["capacity_used_percent"] == pytest.approx(100 * len(stored) / 261)
    assert minimum_gross_rate(pixels, 0, True) == "0.0025"


def test_auto_uses_exact_minimum_rate_and_reports_it(tmp_path, monkeypatch, capsys):
    image, message, key, output = (tmp_path / name for name in
                                   ("cover.png", "message.bin", "key.bin", "stego.png"))
    image.write_bytes(encode_png(np.random.default_rng(126).integers(10, 245, (512, 512), dtype=np.uint8)))
    message.write_bytes(bytes(range(20)))
    key.write_bytes(bytes(range(32)))
    log_report = tmp_path / "automatic.json"
    monkeypatch.setattr(sys, "argv", ["stegolab", "embed", str(image), "--message", str(message),
                                     "--key", str(key), "--output", str(output), "--rate", "auto",
                                     "--output-logs", str(log_report)])
    main()
    captured = capsys.readouterr()
    assert "Suggested minimum gross rate: 0.00262452 bpp" in captured.err
    assert "Chosen gross rate: 0.00262452 bpp" in captured.err
    assert captured.out == ""
    report = json.loads(log_report.read_text(encoding="utf-8"))
    assert report["rate"] == "0.00262452"
    assert report["suggested_rate"] == "0.00262452"
    assert Profile("43/16384").capacity(512 * 512) - 66 == 20
    assert extract_and_decrypt(output.read_bytes(), key.read_bytes(),
                               Profile(report["rate"])) == message.read_bytes()


def test_extract_rejects_auto_rate_without_creating_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / "message.bin"
    monkeypatch.setattr(sys, "argv", ["stegolab", "extract", "not-needed.png", "--output",
                                     str(output), "--rate", "auto"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert "--rate auto is only for analyze/embed" in capsys.readouterr().err
    assert not output.exists()


def test_auto_rejects_payload_above_maximum_supported_rate(tmp_path, monkeypatch, capsys):
    from stegolab import system
    image, message, key, output = (tmp_path / name for name in
                                   ("cover.png", "message.bin", "key.bin", "stego.png"))
    image.write_bytes(encode_png(np.random.default_rng(127).integers(10, 245, (512, 512), dtype=np.uint8)))
    message.write_bytes(np.random.default_rng(128).bytes(7000))
    key.write_bytes(bytes(range(32)))
    monkeypatch.setattr(system, "compute_costs", lambda _: pytest.fail("cost map computed for oversized payload"))
    monkeypatch.setattr(sys, "argv", ["stegolab", "embed", str(image), "--message", str(message),
                                     "--key", str(key), "--output", str(output), "--rate", "auto"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "Chosen gross rate: 0.21563721 bpp" in captured.err
    assert "UNSUPPORTED" in captured.err
    assert "maximum at 0.2 bpp is 6487 bytes" in captured.err
    assert not output.exists()


def test_keygen_optional_json_report(tmp_path, monkeypatch, capsys):
    key, log_report = tmp_path / "private.key", tmp_path / "keygen.json"
    monkeypatch.setattr(sys, "argv", ["stegolab", "keygen", str(key), "--output-logs", str(log_report)])
    main()
    captured = capsys.readouterr()
    report = json.loads(log_report.read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["action"] == "keygen"
    assert report["bytes"] == 32
    assert report["output"] == str(key)
    assert report["seconds"] >= 0
    assert captured.out == ""
    assert "JSON log report saved:" in captured.err
    assert key.read_bytes().hex() not in log_report.read_text(encoding="utf-8")


@pytest.mark.parametrize("destination", ["existing", "same", "missing-parent"])
def test_log_destination_safety_before_key_generation(tmp_path, monkeypatch, capsys, destination):
    from stegolab import cli
    key = tmp_path / "private.key"
    log_report = tmp_path / "report.json"
    if destination == "existing":
        log_report.write_text("keep this file", encoding="utf-8")
    elif destination == "same":
        log_report = key
    else:
        log_report = tmp_path / "missing" / "report.json"
    monkeypatch.setattr(cli.secrets, "token_bytes", lambda _: pytest.fail("generated key for invalid log destination"))
    monkeypatch.setattr(sys, "argv", ["stegolab", "keygen", str(key), "--output-logs", str(log_report)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not key.exists()
    if destination == "existing":
        assert log_report.read_text(encoding="utf-8") == "keep this file"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
