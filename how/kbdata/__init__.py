"""Extra knowledge, one module per area. Each module defines RAW = [(cmd, desc, why, tags), ...]."""
import importlib
import pkgutil


def modules():
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        yield importlib.import_module(f"{__name__}.{info.name}")
