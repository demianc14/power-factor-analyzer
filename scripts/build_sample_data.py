"""Genera los xlsx de ejemplo en data/sample/. Todos los datos son FICTICIOS.

- coil_sample.xlsx: las 5 filas de la plantilla COIL (mismos valores y tipos:
  `fp_actual` como texto), con el nombre de cliente anonimizado. Incluye las
  hojas 2 y 3 como en la plantilla (Hoja 2 con el ahorro/ROI prellenados).
- stress_cases.xlsx: casos de estrés (inspirados en la Semana 4) para ejercitar
  el reporte de calidad: FP en porcentaje, FP corrupto, kW negativo, etc.

Uso: python scripts/build_sample_data.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"

COLS = [
    "id_registro", "cliente", "mes", "anio", "consumo_total_kwh", "demanda_max_kw",
    "consumo_reactivo_kvarh", "fp_actual", "subtotal", "costo_banco_capturado_mxn",
    "fuente_datos", "observaciones", "texto_recibo_original", "captura_manual_validada",
    "pdf_nombre",
]


def _row(id_registro: str, cliente: str, mes: int, kwh: float, kw: Any, kvarh: float,
         fp: Any, subtotal: Any, costo: float, obs: str, texto: str = "") -> list[Any]:
    return [id_registro, cliente, float(mes), 2026.0, float(kwh), kw, float(kvarh), fp,
            subtotal, float(costo), "ficticio", obs, texto or f"RECIBO FICTICIO {id_registro}",
            "SI", f"{id_registro.lower()}.pdf"]


def template_rows() -> list[list[Any]]:
    a, m = "Cliente A (ficticio)", "Cliente B (ficticio)"
    return [
        _row("ARNESES_202601", a, 1, 128500, 420.0, 68400, "0.84", 198500.0, 92000,
             "Caso de prueba 1", "RECIBO FICTICIO A1"),
        _row("ARNESES_202602", a, 2, 131200, 430.0, 64100, "0.87", 201300.0, 92000,
             "Caso de prueba 2", "RECIBO FICTICIO A2"),
        _row("ARNESES_202603", a, 3, 126900, 415.0, 59200, "0.90", 196100.0, 92000,
             "Caso de prueba 3", "RECIBO FICTICIO A3"),
        _row("METALBAJIO_202601", m, 1, 98500, 310.0, 50100, "0.88", 148700.0, 70000,
             "Caso de prueba 4", "RECIBO FICTICIO M1"),
        _row("METALBAJIO_202602", m, 2, 100800, 325.0, 43800, "0.93", 152900.0, 70000,
             "Caso de prueba 5", "RECIBO FICTICIO M2"),
    ]


def stress_rows() -> list[list[Any]]:
    c = "Cliente Stress (ficticio)"
    base: dict[str, Any] = {"kwh": 40000, "kw": 71.0, "kvarh": 18900, "subtotal": 100000.0,
                            "costo": 85000}

    def r(id_registro: str, mes: int, fp: Any, obs: str, **kw: Any) -> list[Any]:
        v = {**base, **kw}
        return _row(id_registro, c, mes, v["kwh"], v["kw"], v["kvarh"], fp, v["subtotal"],
                    v["costo"], obs)

    return [
        r("STRESS_202601", 1, "0.9048", "Caso base válido"),
        r("STRESS_202602", 2, "90.48", "FP capturado como porcentaje"),
        r("STRESS_202603", 3, "1.2", "FP corrupto (no es porcentaje)"),
        r("STRESS_202604", 4, "0.9048", "kW negativo", kw=-71.0),
        r("STRESS_202605", 5, "0", "FP cero"),
        r("STRESS_202606", 6, "n/d", "FP no numérico"),
        r("STRESS_202607", 7, "0.91", "Subtotal faltante", subtotal=None),
        r("STRESS_202608", 8, "0.93", "Válido con FP > 0.90", kvarh=15811),
        r("STRESS_202608", 8, "0.93", "Válido con FP > 0.90", kvarh=15811),  # duplicado exacto
        r("STRESS_202609", 9, "0.96", "Meta ya cumplida", kvarh=11667),
        r("STRESS_202610", 10, "150", "FP fuera de toda escala"),
    ]


def write_template_like(path: Path, rows: list[list[Any]], prefill: bool) -> None:
    hoja1 = pd.DataFrame(rows, columns=COLS)
    cols2 = ["id_registro", "estado_fp", "comentario_diagnostico", "penalizacion_mxn",
             "bonificacion_mxn", "impacto_neto_mxn", "fp_objetivo", "q_requerida_kvar",
             "capacitancia_uf", "tamano_comercial_sugerido_kvar",
             "ahorro_mensual_estimado_mxn", "roi_meses"]
    hoja2 = pd.DataFrame(columns=cols2)
    if prefill:
        # Valores prellenados de la plantilla original (fórmula simplificada).
        prellenado = [(13233.33, 6.95), (6710.0, 13.71), (0.0, ""), (3304.44, 21.18),
                      (5096.67, 13.73)]
        hoja2 = pd.DataFrame(
            [[row[0], *[""] * 9, ahorro, roi] for row, (ahorro, roi) in zip(rows, prellenado,
                                                                           strict=True)],
            columns=cols2,
        )
    hoja3 = pd.DataFrame(columns=["id_registro", "cliente", "fp_actual", "estado_fp",
                                  "impacto_neto_mxn", "tamano_comercial_sugerido_kvar",
                                  "roi_meses", "resumen_reporte", "fecha_ultima_actualizacion"])
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        hoja1.to_excel(w, sheet_name="Hoja 1", index=False)
        hoja2.to_excel(w, sheet_name="Hoja 2", index=False)
        hoja3.to_excel(w, sheet_name="Hoja 3", index=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_template_like(OUT / "coil_sample.xlsx", template_rows(), prefill=True)
    write_template_like(OUT / "stress_cases.xlsx", stress_rows(), prefill=False)
    print(f"Escritos en {OUT}")


if __name__ == "__main__":
    main()
