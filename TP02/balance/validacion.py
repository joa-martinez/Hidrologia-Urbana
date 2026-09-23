"""Advertencias sobre un Caso resuelto.

Ninguna frena el cálculo: los datos imposibles ya los rechazó el modelo.
"""

from __future__ import annotations

from .modelo import POR_CLAVE, Resultado

UMBRAL_RESIDUO_PCT = 5.0


def advertencias(resultado: Resultado, umbral_residuo_pct: float = UMBRAL_RESIDUO_PCT) -> list[str]:
    avisos: list[str] = []
    caso = resultado.caso

    if resultado.clave_cierre is None:
        if abs(resultado.residuo_pct) > umbral_residuo_pct:
            avisos.append(
                f"El balance no cierra: residuo de {resultado.residuo_mm:.1f} mm/año "
                f"({resultado.residuo_pct:.1f} % de las entradas), por encima del "
                f"umbral de {umbral_residuo_pct:.1f} %."
            )
    else:
        valor = resultado.valores[resultado.clave_cierre]
        if valor < 0:
            avisos.append(
                f"La componente de cierre «{POR_CLAVE[resultado.clave_cierre].etiqueta}» "
                f"da negativa ({valor:.1f} mm/año): las hipótesis del caso no cierran."
            )

    if caso.estado == "post":
        if resultado.valores["agua_potable"] == 0:
            avisos.append("El caso está urbanizado pero la provisión de agua potable es nula.")
        elif caso.saneamiento == "ninguno" and resultado.efluente_cloacal > 0:
            avisos.append(
                f"El caso no declara saneamiento: el efluente cloacal "
                f"({resultado.efluente_cloacal:.0f} mm) no sale por ningún lado y "
                "termina dentro del cierre."
            )
        if caso.saneamiento != "ninguno" and resultado.efluente_cloacal == 0:
            avisos.append(
                "El caso tiene saneamiento pero la fracción de efluente cloacal es nula."
            )

    return avisos
