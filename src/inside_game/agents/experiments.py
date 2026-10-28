"""EXPERIMENTO LOCAL (no subir): cambios activables para probar modelos locales.

INSIDE_GAME_EXPERIMENTS=subset,fastpath,delta,slow
INSIDE_GAME_EXPERIMENT_TIME_SCALE=5   # factor de los plazos con "slow"
"""

import os


def experiment(name):
    return name in os.getenv("INSIDE_GAME_EXPERIMENTS", "").split(",")


def T(seconds):
    """Escala un plazo fijo cuando el experimento "slow" está activo."""
    if not experiment("slow"):
        return seconds
    return seconds * float(os.getenv("INSIDE_GAME_EXPERIMENT_TIME_SCALE", "5"))


TOPOLOGY_WORDS = (
    "forma",
    "espacio",
    "estructura",
    "voronoi",
    "topolog",
    "conectiv",
    "proximidad",
    "compact",
    "robustez",
    "bloque",
    "cobertura",
    "persisten",
)
TOPOLOGY_TOOLS = {
    "get_team_shape",
    "get_proximity_connectivity",
    "get_space_coverage",
    "get_persistent_structure",
    "get_node_removal_robustness",
}


def wants_topology(text):
    """La petición pide análisis espacial/topológico de forma explícita."""
    text = text.lower()
    return any(word in text for word in TOPOLOGY_WORDS)


# Gráficos que el usuario pide de forma explícita: (palabras clave, receta, etiqueta).
REQUESTED_VISUALS = [
    (
        ("mapa de tiros", "mapa de remates", "dónde tir", "donde tir"),
        "shot_map",
        "mapa de tiros",
    ),
    (("xg", "goles esperados"), "xg_story", "evolución del xG"),
    (
        ("cronolog", "línea de tiempo", "linea de tiempo"),
        "match_timeline",
        "cronología",
    ),
    (("mapa de pases",), "pass_map", "mapa de pases"),
    (("red de pases", "conexiones", "red de conex"), "passing_network", "red de pases"),
    (
        ("balón parado", "balon parado", "córner", "corner", "secuencia"),
        "sequence_explorer",
        "secuencias",
    ),
    (("defens", "duelo"), "defensive_actions", "acciones defensivas"),
    (
        ("presión", "presion", "recuperaci"),
        "pressure_recovery",
        "presión y recuperación",
    ),
    (("regate", "conducci"), "ball_progression", "regates y conducciones"),
    (("mapa de calor", "ocupaci"), "occupation_heatmap", "mapa de ocupación"),
    (
        ("forma del bloque", "forma del equipo", "bloque defensivo", "compacidad"),
        "team_shape",
        "forma del bloque",
    ),
    (("voronoi", "partición", "particion"), "space_partition", "partición Voronoi"),
    (("compar",), "entity_comparison", "comparación"),
]


def requested_visuals(text):
    """Gráficos pedidos por palabras clave o por su identificador técnico."""
    text = text.lower()
    return [
        (recipe, label)
        for keywords, recipe, label in REQUESTED_VISUALS
        if recipe in text or any(k in text for k in keywords)
    ]


ORIGINAL_QUESTION = "\nPregunta original del usuario: "


def with_original_question(request_text, question):
    """EXPERIMENTO LOCAL "fastpath": Data recibe también la pregunta del usuario,
    para decidir el atajo con ella y no con la reformulación del intérprete."""
    if not experiment("fastpath") or not question.strip():
        return request_text
    return (request_text + ORIGINAL_QUESTION + question.strip())[:8000]


def original_question(request_text):
    """Pregunta original si el chat la añadió; si no, el texto completo."""
    return request_text.split(ORIGINAL_QUESTION, 1)[-1]


# EXPERIMENTO LOCAL "guards": la palabra que sigue a una cifra citada debe
# corresponder a lo que mide ese hecho ("{{goles}} tiros" se rechaza).
METRIC_NOUNS = [
    (("tiro", "remate", "disparo"), ("shot",)),
    (("gol",), ("goal",)),
    (("xg",), ("xg",)),
]


def label_mismatches(text, facts_by_id, token):
    """Pares (fact_id, etiqueta, palabra) cuya palabra no encaja con la etiqueta."""
    problems = []
    for found in token.finditer(text):
        fact = facts_by_id.get(found.group(1))
        if fact is None:
            continue
        label = fact.label.lower()
        following = text[found.end() : found.end() + 14].lower().split()[:2]
        for word in following:
            for nouns, labels in METRIC_NOUNS:
                if any(word.startswith(n) for n in nouns):
                    if not any(part in label for part in labels) or (
                        "goal" in labels and "xg" in label
                    ):
                        problems.append((found.group(1), fact.label, word))
                    break
            else:
                continue
            break
    return problems
