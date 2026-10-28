"""Analyst findings con fuentes desplegables; preserva el texto original."""

from .atoms import text


def analyst_copy(value):
    # Existing reports may contain the original Spanish section separators.
    reference_heading = "\nReferences\n" if "\nReferences\n" in value else "\nReferencias\n"
    body, separator, references = value.partition(reference_heading)
    limit_heading = "\nScope and limitations\n" if "\nScope and limitations\n" in body else "\nAlcance y límites\n"
    body, limits_separator, limits = body.partition(limit_heading)
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
                '<details class="analysis-details"><summary>Scope and limitations</summary>'
                + f'<p class="analyst-copy">{text(remaining)}</p></details>'
            )
    if separator:
        paragraphs.append(
            '<details class="analysis-details"><summary>Sources and references</summary>'
            + f'<p class="analyst-copy">{text(references)}</p></details>'
        )
    return "".join(paragraphs)
