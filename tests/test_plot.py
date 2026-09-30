from pathlib import Path

import pytest

from power_factor.analysis import RecordAnalysis, analyze_record
from power_factor.config import Settings
from power_factor.plot import contiguous_segments, plot_fp_trend
from power_factor.schemas import BillingRecord


def _analysis(mes: int, fp: float, cliente: str = "C", anio: int = 2026) -> RecordAnalysis:
    rec = BillingRecord(
        id_registro=f"{cliente}_{anio}{mes:02d}", cliente=cliente, mes=mes, anio=anio,
        consumo_total_kwh=None, demanda_max_kw=100.0, consumo_reactivo_kvarh=None,
        fp_actual=fp, subtotal=1000.0, costo_banco_capturado_mxn=1000.0, fila_excel=2,
    )
    return analyze_record(rec, Settings())


@pytest.mark.parametrize(
    ("indices", "expected"),
    [
        ([], []),
        ([5], [[5]]),
        ([1, 2, 3], [[1, 2, 3]]),
        ([1, 2, 4, 5, 7], [[1, 2], [4, 5], [7]]),
    ],
)
def test_contiguous_segments_do_not_bridge_gaps(
    indices: list[int], expected: list[list[int]]
) -> None:
    assert contiguous_segments(indices) == expected


def test_segments_across_year_boundary() -> None:
    dic, ene = 2025 * 12 + 11, 2026 * 12 + 0
    assert contiguous_segments([dic, ene]) == [[dic, ene]]


def test_plot_writes_png_with_gaps_and_unsorted_input(tmp_path: Path) -> None:
    analyses = [_analysis(3, 0.9), _analysis(1, 0.84), _analysis(7, 0.96),
                _analysis(1, 0.1, cliente="D")]
    path = plot_fp_trend(analyses, 0.95, tmp_path / "out" / "fp.png")
    assert path.exists() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_plot_many_periods_labels_selectively(tmp_path: Path) -> None:
    analyses = [_analysis(m, 0.85 + m / 100) for m in range(1, 13)]
    analyses += [_analysis(1, 0.9, anio=2027)]
    assert plot_fp_trend(analyses, 0.95, tmp_path / "fp.png").exists()


def test_plot_requires_data(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plot_fp_trend([], 0.95, tmp_path / "fp.png")
