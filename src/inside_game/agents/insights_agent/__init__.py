"""Agente de insights: intención → evidencia exacta → informe y respuesta.

El LLM sólo produce una `InsightIntent` y redacta la respuesta final. Lo que tiene
una respuesta correcta (recetas posibles por fuente, parámetros, ventanas y
consultas) lo decide código determinista. Ver docs/insights-availability.md.
"""
