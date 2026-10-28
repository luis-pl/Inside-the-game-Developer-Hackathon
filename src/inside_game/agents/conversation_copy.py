"""Respuestas breves a partir de texto ya validado; no calcula ni inventa hechos."""

import re

from inside_game.language import wording


def concept_reply(topic, draft, selected_matches=(), *, language="es"):
    t = lambda key: wording(key, language)
    if topic == "welcome":
        lead = t("welcome_selected") if selected_matches else t("welcome_here")
        return (
            lead
            + t("welcome_explore")
            + "\n\n"
            + (t("welcome_follow") if selected_matches else t("welcome_choose"))
        )
    if topic == "xg":
        reply = t("xg")
        if selected_matches and all(
            m.get("provider") in {"Metrica Sports", "SkillCorner"}
            or m.get("data_kind") == "real_anonymized"
            for m in selected_matches
        ):
            reply += "\n\n" + t("xg_missing")
        else:
            reply += "\n\n" + t("xg_synthetic")
        return reply
    if topic == "voronoi":
        return t("voronoi")
    return draft


def catalog_reply(introduction, matches, *, language="es"):
    names = [
        f"{match['home_team_name']} — {match['away_team_name']}"
        for match in matches[:5]
        if match.get("home_team_name") and match.get("away_team_name")
    ]
    parts = [introduction]
    if names:
        parts.append(
            wording("catalog_start", language)
            + "\n"
            + "\n".join(f"• {name}" for name in names)
        )
    parts.append(wording("catalog_end", language))
    return "\n\n".join(parts)


def report_reply(analysis, *, reused=False, partial=False, language="es"):
    if reused:
        return wording("reused", language)
    statements = []
    if analysis and analysis.status in {"complete", "partial"}:
        for section in analysis.sections:
            if re.search(
                r"context|alcance|fuentes|referenc|référenc|referênc|límit|limita|scope|sources|fontes|fonti|quellen|umfang|einschränk",
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
        lead = wording("synthetic_lead", language) if synthetic else ""
        reply = lead + "\n\n".join(statements)
        if partial:
            reply += "\n\n" + wording("partial_note", language)
        return reply + "\n\n" + wording("report_explore", language)
    if partial:
        return wording("report_partial", language)
    return wording("report_ready", language)
