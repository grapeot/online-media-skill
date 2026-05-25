from __future__ import annotations

import csv
from pathlib import Path

from scripts.audio_tags import INVENTORY_COLUMNS
from scripts.music_library_dedup import build_parser, command_build_review, command_read_tags


def test_build_parser_has_read_tags_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["read-tags", "--output", "tmp.csv"])
    assert args.command == "read-tags"
    assert args.output == Path("tmp.csv")


def test_build_parser_has_build_review_command() -> None:
    parser = build_parser()
    args = parser.parse_args(["build-review", "--inventory", "inventory.csv"])
    assert args.command == "build-review"
    assert args.inventory == Path("inventory.csv")


def test_read_tags_reports_missing_root(tmp_path: Path, capsys) -> None:
    missing_root = tmp_path / "missing"
    output_path = tmp_path / "inventory.csv"
    args = type(
        "Args",
        (),
        {
            "roots": [missing_root],
            "output": output_path,
        },
    )()
    exit_code = command_read_tags(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "missing_root=" in captured.out
    assert output_path.exists()
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []
