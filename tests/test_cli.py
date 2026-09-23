import sys

import pytest

from stegolab.cli import main
from stegolab.system import ExtractionError, extract_and_decrypt


def test_keygen_refuses_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "key.bin"
    monkeypatch.setattr(sys, "argv", ["stegolab", "keygen", str(path)])
    main()
    original = path.read_bytes()
    assert len(original) == 32
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert path.read_bytes() == original


def test_failed_extraction_has_no_output(tmp_path, monkeypatch, capsys):
    image, key, output = (tmp_path / name for name in ("bad.png", "key.bin", "message.bin"))
    image.write_bytes(b"\x89PNG\r\n\x1a\ntruncated")
    key.write_bytes(bytes(32))
    monkeypatch.setattr(sys, "argv", ["stegolab", "extract", str(image), "--key", str(key),
                                     "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not output.exists()
    stderr = capsys.readouterr().err
    assert "No valid authenticated payload" in stderr
    assert "Traceback" not in stderr


def test_malformed_images_share_generic_failure():
    for data in (b"", b"not png", b"\x89PNG\r\n\x1a\ntruncated"):
        with pytest.raises(ExtractionError, match="^No valid authenticated payload$") as error:
            extract_and_decrypt(data, bytes(32))
        assert error.value.__suppress_context__
