"""Gráfica de tendencia del FP por cliente: barras + línea contra la meta.

- Un panel por cliente, periodos en orden cronológico.
- Los meses faltantes NO se inventan: el eje muestra el hueco ("sin dato") y
  la línea se corta ahí en vez de unir los puntos vecinos.
- Las barras arrancan en 0 (una barra con eje truncado exagera diferencias).
- Usa la API orientada a objetos (`Figure`), sin estado global de pyplot.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from power_factor.analysis import RecordAnalysis

SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#8a8985"
GRID = "#e8e7e3"
BAR = "#9ec5f4"
LINE = "#2a78d6"

# Con más periodos que esto solo se etiquetan el último y el mínimo.
MAX_LABELED_POINTS = 12
# Debajo de este FP la barra es muy corta para llevar la etiqueta dentro.
INSIDE_LABEL_MIN_FP = 0.2


def contiguous_segments(indices: Sequence[int]) -> list[list[int]]:
    """Parte una secuencia ordenada de meses en tramos sin huecos.

    [1, 2, 4, 5, 7] -> [[1, 2], [4, 5], [7]]
    """
    segmentos: list[list[int]] = []
    for i in indices:
        if segmentos and i == segmentos[-1][-1] + 1:
            segmentos[-1].append(i)
        else:
            segmentos.append([i])
    return segmentos


def _period_label(indice_mes: int) -> str:
    anio, mes0 = divmod(indice_mes, 12)
    return f"{anio}-{mes0 + 1:02d}"


def plot_fp_trend(
    analyses: Sequence[RecordAnalysis],
    fp_objetivo: float,
    path: str | Path,
    umbral: float = 0.90,
) -> Path:
    if not analyses:
        raise ValueError("No hay registros válidos para graficar")
    por_cliente: dict[str, list[RecordAnalysis]] = defaultdict(list)
    for a in analyses:
        por_cliente[a.record.cliente].append(a)

    n = len(por_cliente)
    fig = Figure(figsize=(10, 3.0 * n), facecolor=SURFACE, layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(n, 1, squeeze=False)[:, 0]

    for ax, (cliente, items) in zip(axes, sorted(por_cliente.items()), strict=True):
        items = sorted(items, key=lambda a: a.record.indice_mes)
        fp_por_mes = {a.record.indice_mes: a.record.fp_actual for a in items}
        meses = sorted(fp_por_mes)

        ax.set_facecolor(SURFACE)
        ax.bar(meses, [fp_por_mes[m] for m in meses], width=0.3, color=BAR, zorder=2)
        for seg in contiguous_segments(meses):
            ax.plot(seg, [fp_por_mes[m] for m in seg], color=LINE, linewidth=2,
                    marker="o", markersize=8, markeredgecolor=SURFACE, markeredgewidth=2,
                    solid_capstyle="round", zorder=3)

        etiquetar = meses if len(meses) <= MAX_LABELED_POINTS else sorted(
            {meses[-1], min(meses, key=lambda m: fp_por_mes[m])})
        for m in etiquetar:
            # Dentro de la barra, bajo el marcador: arriba viven las líneas de meta/umbral.
            dentro = fp_por_mes[m] > INSIDE_LABEL_MIN_FP
            ax.annotate(f"{fp_por_mes[m]:.3f}", (m, fp_por_mes[m]),
                        xytext=(0, -16 if dentro else 9), textcoords="offset points",
                        ha="center", va="center", fontsize=9, color=TEXT_PRIMARY, zorder=4)

        for nivel, texto, estilo in ((fp_objetivo, f"Meta {fp_objetivo:.2f}", "--"),
                                     (umbral, f"Umbral CFE {umbral:.2f}", ":")):
            ax.axhline(nivel, color=TEXT_SECONDARY, linewidth=1, linestyle=estilo, zorder=1)
            ax.annotate(texto, (1.0, nivel), xycoords=("axes fraction", "data"),
                        xytext=(4, 0), textcoords="offset points", va="center",
                        fontsize=8, color=TEXT_SECONDARY)

        rango = list(range(meses[0], meses[-1] + 1))
        ax.set_xticks(rango)
        ax.set_xticklabels([_period_label(m) if m in fp_por_mes
                            else f"{_period_label(m)}\nsin dato" for m in rango], fontsize=9)
        for tick, m in zip(ax.get_xticklabels(), rango, strict=True):
            tick.set_color(TEXT_SECONDARY if m in fp_por_mes else TEXT_MUTED)
        ax.set_xlim(meses[0] - 0.75, meses[-1] + 0.75)
        ax.set_ylim(0, 1.08)
        ax.set_ylabel("Factor de potencia", color=TEXT_SECONDARY, fontsize=9)
        ax.set_title(f"{cliente}: FP por periodo", loc="left", color=TEXT_PRIMARY,
                     fontsize=11)
        ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-", zorder=0)
        ax.tick_params(colors=TEXT_SECONDARY, length=0)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    return path
