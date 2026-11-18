"""A permissive fake of PySide6 used ONLY by the UI smoke test.

Every Qt class is a dummy that accepts any call. This catches NameError/AttributeError/typo/
signature problems in our own UI code when constructing pages. It cannot validate real Qt
behaviour or API correctness - that needs a real PySide6 run (see docs/KNOWN_ISSUES.md).
"""
from __future__ import annotations

import sys
import types


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Meta(name, (_Dummy,), {})
        setattr(cls, name, sub)
        return sub

    def __or__(cls, other):
        return cls

    def __iter__(cls):
        return iter(())


class _Dummy(metaclass=_Meta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        d = _Dummy()
        object.__setattr__(self, name, d)
        return d

    def __call__(self, *a, **k):
        return _Dummy()

    def __bool__(self):
        return False      # falsy so `while layout.count():` style loops terminate

    def __or__(self, other):
        return self

    __ror__ = __or__

    def __iter__(self):
        return iter(())

    def __getitem__(self, k):
        return _Dummy()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    def __lt__(self, o): return False
    def __gt__(self, o): return False
    def __le__(self, o): return False
    def __ge__(self, o): return False
    def __add__(self, o): return 0
    def __radd__(self, o): return 0
    def __sub__(self, o): return 0
    def __rsub__(self, o): return 0
    def __mul__(self, o): return 0
    def __rmul__(self, o): return 0
    def __floordiv__(self, o): return 0
    def __truediv__(self, o): return 0
    def __mod__(self, o): return 0

    def __str__(self):
        return ""


class _Signal:
    def __init__(self, *a, **k):
        self._slots = []

    def connect(self, fn, *a, **k):
        self._slots.append(fn)

    def disconnect(self, *a):
        pass

    def emit(self, *a):
        for fn in list(self._slots):
            fn(*a)

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        d = obj.__dict__.setdefault("_sigs", {})
        return d.setdefault(id(self), _Signal())


def _module(name: str) -> types.ModuleType:
    m = types.ModuleType(name)

    def getattr_(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        if attr == "Signal":
            return _Signal
        cls = _Meta(attr, (_Dummy,), {})
        setattr(m, attr, cls)
        return cls

    m.__getattr__ = getattr_  # type: ignore[attr-defined]
    return m


def install() -> dict[str, types.ModuleType]:
    mods = {"PySide6": _module("PySide6")}
    for sub in ("QtCore", "QtGui", "QtWidgets"):
        mods[f"PySide6.{sub}"] = _module(f"PySide6.{sub}")
        setattr(mods["PySide6"], sub, mods[f"PySide6.{sub}"])
    sys.modules.update(mods)
    return mods


def uninstall() -> None:
    for name in list(sys.modules):
        if name == "PySide6" or name.startswith("PySide6.") or name.startswith("proconvert.ui."):
            del sys.modules[name]
    sys.modules.pop("proconvert.ui", None)
