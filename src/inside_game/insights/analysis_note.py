"""Lectura del analista con fuentes desplegables; preserva el texto original."""

from .atoms import text


def analyst_copy(value):
    body, separator, references = value.partition("\nReferencias\n")
    body, limits_separator, limits = body.partition("\nAlcance y límites\n")
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
                '<details class="analysis-details"><summary>Alcance y límites</summary>'
                + f'<p class="analyst-copy">{text(remaining)}</p></details>'
            )
    if separator:
        paragraphs.append(
            '<details class="analysis-details"><summary>Fuentes y referencias</summary>'
            + f'<p class="analyst-copy">{text(references)}</p></details>'
        )
    return "".join(paragraphs)
