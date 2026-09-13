"""Require a release tag to identify exactly the compiled crate version."""
import sys
import tomllib
from pathlib import Path
version = tomllib.loads(Path('Cargo.toml').read_text())['package']['version']
if sys.argv[1] != 'v' + version:
    raise SystemExit(f'Tag must be v{version}, matching Cargo.toml')
