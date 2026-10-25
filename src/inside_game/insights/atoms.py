"""Átomos HTML/SVG. Todo texto externo se escapa; números no finitos se rechazan."""

from html import escape
from math import isfinite


def text(value):
    return escape(str(value), quote=True)


def numeric(value):
    if type(value) not in (int, float) or not isfinite(value):
        return "—"
    return (
        f"{value:,.3f}".rstrip("0").rstrip(".")
        if isinstance(value, float)
        else str(value)
    )


def status(value):
    labels = {
        "ready": "Disponible",
        "partial": "Parcial",
        "unavailable": "No disponible",
        "incompatible": "Incompatible",
        "error": "Error",
        "empty_with_coverage": "Vacío · revisar cobertura",
    }
    return f'<span class="status {text(value)}">{labels[value]}</span>'


def point(x, y, label="", color="#185540"):
    return f'<circle cx="{float(x):.4f}" cy="{float(y):.4f}" r="1.0" fill="{color}" stroke="#fff" stroke-width=".18"><title>{text(label)}</title></circle>'


def vector(x, y, end_x, end_y):
    return f'<path d="M {float(x):.4f} {float(y):.4f} L {float(end_x):.4f} {float(end_y):.4f}" class="vector"/>'


MARKINGS = '<rect width="105" height="68"/><path d="M52.5 0V68 M0 13.84H16.5V54.16H0 M105 13.84H88.5V54.16H105 M0 24.84H5.5V43.16H0 M105 24.84H99.5V43.16H105"/><circle cx="52.5" cy="34" r="9.15"/><circle cx="11" cy="34" r=".35"/><circle cx="94" cy="34" r=".35"/>'
