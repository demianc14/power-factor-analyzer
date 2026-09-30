import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from power_factor.cli import EXIT_INPUT_ERROR, EXIT_OK, build_parser, main, settings_from_args
from tests.conftest import base_row


def test_cli_runs_on_sample(sample_xlsx: Path, tmp_path: Path,
                            capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "analisis.xlsx"
    code = main(["run", "--input", str(sample_xlsx), "--output", str(out),
                 "--fecha", "2026-09-30"])
    assert code == EXIT_OK
    salida = capsys.readouterr().out
    assert "filas_originales" in salida and "ARNESES_202601" in salida
    assert "gráfica:" in salida
    assert out.exists()


def test_cli_preset_and_overrides() -> None:
    args = build_parser().parse_args(["run", "--input", "x.xlsx", "--preset", "480_delta",
                                      "--fp-objetivo", "0.97", "--negative-kw-policy", "abs"])
    s = settings_from_args(args)
    assert (s.voltaje_v, s.conexion, s.fp_objetivo, s.negative_kw_policy) == (
        480, "delta", 0.97, "abs")


def test_cli_invalid_override_fails_fast(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["run", "--input", "x.xlsx", "--fp-objetivo", "1.5"])
    assert code == EXIT_INPUT_ERROR
    assert "fp_objetivo" in capsys.readouterr().err


def test_cli_missing_column_reports_it(tmp_path: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "in.xlsx"
    pd.DataFrame([base_row()]).drop(columns=["subtotal"]).to_excel(
        path, sheet_name="Hoja 1", index=False)
    code = main(["run", "--input", str(path), "--output", str(tmp_path / "o.xlsx"), "--no-plot"])
    assert code == EXIT_INPUT_ERROR
    assert "['subtotal']" in capsys.readouterr().err


def test_cli_missing_file(tmp_path: Path) -> None:
    assert main(["run", "--input", str(tmp_path / "nope.xlsx")]) == EXIT_INPUT_ERROR


def test_module_entrypoint(sample_xlsx: Path, tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "power_factor.cli", "run", "--input", str(sample_xlsx),
         "--output", str(tmp_path / "o.xlsx"), "--no-plot"],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "03_Resultados_Negocio" in proc.stdout
