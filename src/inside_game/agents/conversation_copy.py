"""Respuestas breves a partir de texto ya validado; no calcula ni inventa hechos."""

import re


def concept_reply(topic, draft, selected_matches=()):
    if topic == "welcome":
        lead = "Con el partido que tienes seleccionado" if selected_matches else "Aquí"
        return (
            lead
            + " podemos explorar las ocasiones de gol, cómo circuló el balón y qué espacios dejaron los equipos.\n\n"
            + (
                "Cuéntame qué te gustaría entender del partido."
                if selected_matches
                else "Elige un partido en el selector y cuéntame qué te gustaría entender."
            )
        )
    if topic == "xg":
        reply = "El xG, o goles esperados, estima la probabilidad de que un tiro termine en gol según un modelo. La suma del xG de los tiros ayuda a resumir la calidad de las ocasiones de un equipo. No predice el marcador ni dice cuántos goles debía marcar."
        if selected_matches and all(
            m.get("provider") in {"Metrica Sports", "SkillCorner"}
            or m.get("data_kind") == "real_anonymized"
            for m in selected_matches
        ):
            reply += "\n\nEl partido seleccionado no tiene xG disponible. Sí podemos revisar sus tiros y sus pases."
        else:
            reply += "\n\nEn los partidos sintéticos de esta demo es una medida ilustrativa, no una estimación calibrada para fútbol real."
        return reply
    if topic == "voronoi":
        return "Imagina que asignamos cada punto del campo al jugador que tiene más cerca en ese instante. Ese reparto se llama Voronoi.\n\nSirve para leer distancias y espacios entre jugadores. No demuestra quién controla el balón o domina una zona, ni asegura que un pase sea seguro."
    return draft


def catalog_reply(introduction, matches):
    names = [
        f"{match['home_team_name']} — {match['away_team_name']}"
        for match in matches[:5]
        if match.get("home_team_name") and match.get("away_team_name")
    ]
    parts = [introduction]
    if names:
        parts.append("Puedes empezar por:\n" + "\n".join(f"• {name}" for name in names))
    parts.append("La lista completa está en el selector Partido, debajo del chat.")
    return "\n\n".join(parts)


def report_reply(analysis, *, reused=False, partial=False):
    if reused:
        return "Hecho. El informe ya tiene el cambio que pediste y conserva sus datos y su análisis."
    statements = []
    if analysis and analysis.status in {"complete", "partial"}:
        for section in analysis.sections:
            if re.search(
                r"contexto|alcance|fuentes|referencias|límites",
                section.heading,
                re.IGNORECASE,
            ):
                continue
            statements = [s.text for s in section.statements[:2]]
            if statements:
                break
    if statements:
        # Son las mismas afirmaciones que finish_analysis contrastó con sus facts.
        # La primera sección responde a la pregunta; las fuentes siguen en el informe.
        facts = analysis.facts
        synthetic = facts and all(
            f.provenance.get("is_synthetic") is True for f in facts
        )
        lead = "Con los datos sintéticos de este partido: " if synthetic else ""
        reply = lead + "\n\n".join(statements)
        if partial:
            reply += (
                "\n\nEsta lectura tiene un alcance limitado, explicado en el informe."
            )
        return reply + "\n\nPuedes explorar los gráficos y sus fuentes en el informe."
    if partial:
        return "El informe está disponible, pero no pude completar toda la explicación. Puedes revisar sus gráficos y volver a intentar el análisis."
    return "El informe está listo. Puedes explorar los gráficos y leer el análisis del partido."
