# Local override for PyInstaller's pydantic hook.
# Suppresses the "Core Pydantic V1 not compatible with Python 3.14" warning
# by collecting only pydantic V2 submodules and skipping the V1 compat layer.
import warnings

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    _all = collect_submodules("pydantic")

# Exclude pydantic.v1 — incompatible with Python 3.14
hiddenimports = [m for m in _all if not m.startswith("pydantic.v1")]
datas = collect_data_files("pydantic")
