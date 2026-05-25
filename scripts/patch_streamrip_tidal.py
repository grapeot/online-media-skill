#!/usr/bin/env python3
"""Patch the locally installed streamrip Tidal client when upstream credentials break.

This script intentionally does not ship Tidal client credentials. Provide the
currently valid pair through environment variables in a private shell.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import os
import re
from pathlib import Path
from typing import cast


def streamrip_tidal_path() -> Path:
    spec = importlib.util.find_spec("streamrip.client.tidal")
    if spec is None or spec.origin is None:
        raise RuntimeError("streamrip.client.tidal is not installed in this Python environment")
    return Path(spec.origin)


def encoded_assignment(name: str, value: str) -> str:
    encoded = base64.b64encode(value.encode("iso-8859-1")).decode("ascii")
    return f'{name} = base64.b64decode("{encoded}").decode("iso-8859-1")'


def patch_text(text: str, client_id: str, client_secret: str) -> str:
    text = re.sub(
        r'CLIENT_ID = base64\.b64decode\("[^"]+"\)\.decode\("iso-8859-1"\)',
        encoded_assignment("CLIENT_ID", client_id),
        text,
        count=1,
    )
    text = re.sub(
        r'CLIENT_SECRET = base64\.b64decode\(\n\s+"[^"]+",\n\)\.decode\("iso-8859-1"\)',
        encoded_assignment("CLIENT_SECRET", client_secret),
        text,
        count=1,
    )
    text = text.replace(
        '            except TypeError as e:\n                logger.warning(f"Failed to get lyrics for {item_id}: {e}")\n',
        '            except Exception as e:\n                logger.warning(f"Failed to get lyrics for {item_id}: {e}")\n',
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--dry-run", action="store_true", help="Validate inputs and show target without editing")
    args = parser.parse_args()
    dry_run = cast(bool, getattr(args, "dry_run"))

    client_id = os.environ.get("STREAMRIP_TIDAL_CLIENT_ID")
    client_secret = os.environ.get("STREAMRIP_TIDAL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set STREAMRIP_TIDAL_CLIENT_ID and STREAMRIP_TIDAL_CLIENT_SECRET in a private shell before running this script."
        )

    target = streamrip_tidal_path()
    text = target.read_text(encoding="utf-8")
    patched = patch_text(text, client_id, client_secret)
    if patched == text:
        raise SystemExit("No changes made; streamrip tidal.py may already be patched or its structure changed upstream.")
    if dry_run:
        _ = print(f"would_patch={target}")
        return 0
    _ = target.write_text(patched, encoding="utf-8")
    _ = print(f"patched={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
