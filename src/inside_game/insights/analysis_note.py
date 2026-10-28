"""Lectura del analista con fuentes desplegables; preserva el texto original."""

from typing import get_args

from inside_game.language import Language, wording

from .atoms import text


def analyst_copy(value, *, language="es"):
    def partition_heading(body, key):
        for candidate in dict.fromkeys([language, *get_args(Language)]):
            heading = "\n" + wording(key, candidate) + "\n"
            if heading in body:
                return body.partition(heading)
        return body, "", ""

    body, separator, references = partition_heading(value, "references")
    body, limits_separator, limits = partition_heading(body, "limits")
    paragraphs = []
    for index, paragraph in enumerate(body.strip().split("\n\n")):
        heading, newline, content = paragraph.partition("\n")
        if index and newline and content.strip():
            paragraphs.append(
                f'<h3>{text(heading)}</h3><p class="analyst-copy">{text(content)}</p>'
            )
        else:
            paragraphs.append(f'<p class="analyst-copy">{text(paragraph)}</p>')
    if limits_separator:
        # La limitación principal sigue visible: plegar el detalle no debe ocultar
        # que se trata de una muestra o de una métrica ilustrativa.
        first, _, remaining = limits.strip().partition("\n")
        paragraphs.append(f'<p class="analyst-copy">{text(first)}</p>')
        if remaining:
            paragraphs.append(
                '<details class="analysis-details"><summary>'
                + text(wording("limits", language))
                + "</summary>"
                + f'<p class="analyst-copy">{text(remaining)}</p></details>'
            )
    if separator:
        paragraphs.append(
            '<details class="analysis-details"><summary>'
            + text(wording("sources", language))
            + "</summary>"
            + f'<p class="analyst-copy">{text(references)}</p></details>'
        )
    return "".join(paragraphs)
