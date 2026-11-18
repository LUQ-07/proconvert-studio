"""Original vector icons drawn with QPainter (no third-party icon assets)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Each drawer paints on a 24x24 grid with the pen already set (round caps, no fill).


def _poly(p: QPainter, pts: list[tuple[float, float]], close: bool = False) -> None:
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _home(p):
    _poly(p, [(3, 11), (12, 3), (21, 11)])
    _poly(p, [(5, 10), (5, 21), (19, 21), (19, 10)])
    _poly(p, [(10, 21), (10, 14), (14, 14), (14, 21)])


def _convert(p):
    _poly(p, [(4, 8), (19, 8)])
    _poly(p, [(15, 4), (19, 8), (15, 12)])
    _poly(p, [(20, 16), (5, 16)])
    _poly(p, [(9, 12), (5, 16), (9, 20)])


def _batch(p):
    for dy in (0, 5, 10):
        p.drawRoundedRect(QRectF(4, 4 + dy, 16, 5), 1.5, 1.5)


def _history(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    _poly(p, [(12, 7), (12, 12), (16, 14)])


def _settings(p):
    for y, x in ((7, 9), (12, 15), (17, 8)):
        _poly(p, [(4, y), (20, y)])
        p.drawEllipse(QRectF(x - 2, y - 2, 4, 4))


def _help(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    path = QPainterPath(QPointF(9.5, 9.5))
    path.cubicTo(9.5, 6.5, 14.5, 6.5, 14.5, 9.5)
    path.cubicTo(14.5, 11.5, 12, 11.5, 12, 14)
    p.drawPath(path)
    p.drawPoint(QPointF(12, 17.3))


def _info(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    _poly(p, [(12, 11), (12, 17)])
    p.drawPoint(QPointF(12, 7.5))


def _folder(p):
    _poly(p, [(3, 7), (3, 19), (21, 19), (21, 9), (11, 9), (9, 6), (3, 6)], close=True)


def _file(p):
    _poly(p, [(6, 3), (14, 3), (19, 8), (19, 21), (6, 21)], close=True)
    _poly(p, [(14, 3), (14, 8), (19, 8)])


def _check(p):
    _poly(p, [(4, 12.5), (10, 18), (20, 6)])


def _alert(p):
    _poly(p, [(12, 3), (22, 20), (2, 20)], close=True)
    _poly(p, [(12, 9), (12, 14)])
    p.drawPoint(QPointF(12, 17))


def _x(p):
    _poly(p, [(6, 6), (18, 18)])
    _poly(p, [(18, 6), (6, 18)])


def _plus(p):
    _poly(p, [(12, 5), (12, 19)])
    _poly(p, [(5, 12), (19, 12)])


def _trash(p):
    _poly(p, [(4, 7), (20, 7)])
    _poly(p, [(9, 7), (9, 4), (15, 4), (15, 7)])
    _poly(p, [(6, 7), (7, 21), (17, 21), (18, 7)])


def _download(p):
    _poly(p, [(12, 4), (12, 16)])
    _poly(p, [(7, 11), (12, 16), (17, 11)])
    _poly(p, [(5, 20), (19, 20)])


def _bolt(p):
    _poly(p, [(13, 3), (5, 14), (11, 14), (10, 21), (19, 9), (13, 9)], close=True)


def _image(p):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.drawEllipse(QRectF(7, 8, 3.5, 3.5))
    _poly(p, [(4, 18), (10, 13), (14, 17), (17, 14), (20, 17)])


def _menu(p):
    for y in (6, 12, 18):
        _poly(p, [(4, y), (20, y)])


def _arrow_left(p):
    _poly(p, [(19, 12), (5, 12)])
    _poly(p, [(11, 5), (4.5, 12), (11, 19)])


def _arrow_right(p):
    _poly(p, [(5, 12), (19, 12)])
    _poly(p, [(13, 5), (19.5, 12), (13, 19)])


DRAWERS = {"menu": _menu, "arrow_left": _arrow_left, "arrow_right": _arrow_right, "image": _image, "home": _home, "convert": _convert, "batch": _batch, "history": _history, "settings": _settings,
           "help": _help, "info": _info, "folder": _folder, "file": _file, "check": _check, "alert": _alert,
           "x": _x, "plus": _plus, "trash": _trash, "download": _download, "bolt": _bolt}


def icon(name: str, color: str = "#FFFFFF", size: int = 20) -> QIcon:
    scale = 2  # draw at 2x so the icon stays crisp on high-DPI screens
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size * scale / 24.0, size * scale / 24.0)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    DRAWERS.get(name, _file)(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)
