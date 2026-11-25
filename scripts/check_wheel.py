"""Check that a release wheel contains the expected native modules and bootstrap."""

import sys
from pathlib import Path
from zipfile import ZipFile

version, filename = sys.argv[1:]
wheel = Path(filename)
if not wheel.name.startswith(f"httpcrabber-{version}-cp311-abi3-"):
    raise SystemExit(f"Unexpected release filename: {wheel.name}")
with ZipFile(wheel) as archive:
    files = {p for p in archive.namelist() if p.startswith("httpcrabber/")}
bootstrap = {"httpcrabber/__main__.py", "httpcrabber/__init__.py"}
native = {p for p in files if p.endswith((".so", ".pyd"))}
expected = {p.stem for p in Path("src/httpcrabber").glob("*.py")} - {"__main__", "__init__"}
if files - native != bootstrap or {Path(p).name.split(".")[0] for p in native} != expected:
    raise SystemExit(f"Unexpected wheel contents: {sorted(files)}")
print(f"{wheel.name}: verified {len(native)} native modules")
