"""Respuestas breves a partir de texto ya validado; no calcula ni inventa hechos."""

import re


def concept_reply(topic, draft, selected_matches=()):
    if topic == "welcome":
        lead = "With your selected match" if selected_matches else "Here"
        return (
            lead
            + " we can explore chance creation, ball circulation and the spaces between the teams.\n\n"
            + (
                "Tell me what you would like to understand about the match."
                if selected_matches
                else "Select a match and tell me what you would like to understand."
            )
        )
    if topic == "xg":
        reply = "Expected goals (xG) estimates how likely a shot is to result in a goal according to a model. Adding shot xG helps summarise the quality of a team’s chances. It does not predict the score or say how many goals a team should have scored."
        if selected_matches and all(
            m.get("provider") in {"Metrica Sports", "SkillCorner"}
            or m.get("data_kind") == "real_anonymized"
            for m in selected_matches
        ):
            reply += "\n\nThe selected match has no available xG. We can still review its shots and passes."
        else:
            reply += "\n\nFor synthetic matches in this demo, xG is illustrative and is not calibrated for real football."
        return reply
    if topic == "voronoi":
        return "Imagine assigning each point on the pitch to its nearest player at that instant. This is called a Voronoi partition.\n\nIt helps describe distances and space between players. It does not establish ball control, dominance of a zone or the safety of a pass."
    return draft


def catalog_reply(introduction, matches):
    names = [
        f"{match['home_team_name']} — {match['away_team_name']}"
        for match in matches[:5]
        if match.get("home_team_name") and match.get("away_team_name")
    ]
    parts = [introduction]
    if names:
        parts.append("You could start with:\n" + "\n".join(f"• {name}" for name in names))
    parts.append("The full list is in the Match selector below the chat.")
    return "\n\n".join(parts)


def report_reply(analysis, *, reused=False, partial=False):
    if reused:
        return "Done. The report includes your change and retains its data and analysis."
    statements = []
    if analysis and analysis.status in {"complete", "partial"}:
        for section in analysis.sections:
            if re.search(
                r"context|scope|sources|references|limitations|contexto|alcance|fuentes|referencias|límites",
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
        lead = "Using this match’s synthetic data: " if synthetic else ""
        reply = lead + "\n\n".join(statements)
        if partial:
            reply += (
                "\n\nThis reading has a limited scope, explained in the report."
            )
        return reply + "\n\nExplore the charts and their sources in the report."
    if partial:
        return "The report is available, but the explanation is incomplete. You can review the charts and retry the analysis."
    return "The report is ready. Explore the charts and read the match analysis."
