"""Constructor de dashboards e insights: el agente vive en `agents/insights_agent/`."""

from inside_game.agents.insights_agent.agent import AskResult, InsightsAgent
from inside_game.agents.insights_agent.contracts import AskRequest, InsightAnswer

__all__ = ["AskRequest", "AskResult", "InsightAnswer", "InsightsAgent"]
