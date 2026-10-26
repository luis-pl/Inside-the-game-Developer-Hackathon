"""Fachada de insights: planificación A2A y composición MCP con revisiones."""

from inside_game.agents.insights_agent.agent import AskResult, InsightsAgent
from inside_game.agents.insights_agent.contracts import AskRequest, InsightAnswer
from inside_game.agents.page_builder import DashboardBuilder, InsightLimits

__all__ = [
    "AskRequest",
    "AskResult",
    "DashboardBuilder",
    "InsightAnswer",
    "InsightLimits",
    "InsightsAgent",
]
