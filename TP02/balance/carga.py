"""Lectura y escritura de una Cuenca (con sus estados y casos) en TOML y en CSV/Excel.

Los dos formatos describen lo mismo y pasan por el mismo diccionario intermedio
(ver docs/adr/0001-toml-y-csv-en-paralelo.md). Un archivo es una Cuenca completa:
la comparación entera, no un caso suelto (ver docs/adr/0002-cuenca-estado-caso.md).
"""

from __future__ import annotations

import csv
import io
import json
import tomllib
from pathlib import Path
from typing import Any

from .modelo import (
    ESTADOS,
    UNIDADES_VALOR,
    Caso,
    Cuenca,
    ErrorDeCaso,
    EspecificacionComponente,
    EstadoUrbanizacion,
    Reparto,
)

CAMPOS_CUENCA = ("nombre", "area_km2", "cierre")
CAMPOS_REPARTO = ("fraccion_perdidas_red", "fraccion_efluente_cloacal")
CAMPOS_CASO = ("estado", "saneamiento")
SIN_CIERRE = "ninguno"  # TOML no tiene nulo: así se escribe que no hay cierre

# Columnas del CSV. «ambito» es cuenca, pre, post o caso. «elemento» es la componente
# (vacío para los datos sueltos del ámbito) o, en las filas de caso, el nombre del caso.
COLUMNAS_CSV = ("ambito", "elemento", "campo", "valor")


def desde_dict(crudo: dict[str, Any]) -> Cuenca:
    """Arma una Cuenca desde el diccionario intermedio que producen los dos lectores."""
    estados = {}
    for clave, datos in crudo.get("estados", {}).items():
        reparto = None
        if any(campo in datos for campo in CAMPOS_REPARTO):
            reparto = Reparto(**{c: float(datos[c]) for c in CAMPOS_REPARTO if c in datos})
        estados[clave] = EstadoUrbanizacion(
            clave=clave,
            componentes=_componentes(datos.get("componentes", {})),
            reparto=reparto,
        )
    cierre = crudo.get("cierre")
    return Cuenca(
        nombre=str(crudo.get("nombre", "Sin nombre")),
        area_km2=float(crudo.get("area_km2", 1.0)),
        componentes=_componentes(crudo.get("componentes", {})),
        cierre=None if cierre in (None, "", SIN_CIERRE) else str(cierre),
        estados=estados,
        casos=[
            Caso(
                nombre=str(c.get("nombre", "Sin nombre")),
                estado=str(c.get("estado", "")),  # type: ignore[arg-type]
                saneamiento=str(c.get("saneamiento", "ninguno")),  # type: ignore[arg-type]
            )
            for c in crudo.get("casos", [])
        ],
    )


def a_dict(cuenca: Cuenca) -> dict[str, Any]:
    estados: dict[str, Any] = {}
    for clave in ESTADOS:
        estado = cuenca.estados[clave]
        datos: dict[str, Any] = {}
        if estado.reparto is not None:
            datos["fraccion_perdidas_red"] = estado.reparto.fraccion_perdidas_red
            datos["fraccion_efluente_cloacal"] = estado.reparto.fraccion_efluente_cloacal
        datos["componentes"] = _campos_de(estado.componentes)
        estados[clave] = datos
    return {
        "nombre": cuenca.nombre,
        "area_km2": cuenca.area_km2,
        "cierre": cuenca.cierre or SIN_CIERRE,
        "componentes": _campos_de(cuenca.componentes),
        "estados": estados,
        "casos": [
            {"nombre": c.nombre, "estado": c.estado, "saneamiento": c.saneamiento}
            for c in cuenca.casos
        ],
    }


def _componentes(crudas: dict[str, Any]) -> dict[str, EspecificacionComponente]:
    return {clave: _espec_desde_campos(clave, dict(campos)) for clave, campos in crudas.items()}


def _campos_de(componentes: dict[str, EspecificacionComponente]) -> dict[str, dict[str, Any]]:
    salida: dict[str, dict[str, Any]] = {}
    for clave, esp in componentes.items():
        campos: dict[str, Any] = {}
        if esp.valor is not None:
            campos[esp.campo_valor or "valor_mm"] = esp.valor
        elif esp.metodo is not None:
            campos["metodo"] = esp.metodo
            campos.update(esp.parametros)
        salida[clave] = campos
    return salida


def _espec_desde_campos(clave: str, campos: dict[str, Any]) -> EspecificacionComponente:
    if "cierre" in campos:
        raise ErrorDeCaso(
            f"La componente '{clave}' dice «cierre»: ahora el cierre se elige una sola vez "
            "para toda la cuenca (cierre = \"...\")."
        )
    metodo = campos.pop("metodo", None)
    unidades = [c for c in campos if c in UNIDADES_VALOR or c == "valor"]
    if len(unidades) > 1:
        raise ErrorDeCaso(
            f"La componente '{clave}' define más de un valor: {sorted(unidades)}"
        )
    campo_valor = valor = None
    if unidades:
        campo_valor = unidades[0]
        if campo_valor == "valor":
            raise ErrorDeCaso(
                f"La componente '{clave}' usa 'valor' sin unidad. "
                f"Escribí la unidad en el nombre: {', '.join(UNIDADES_VALOR)}."
            )
        valor = float(campos.pop(campo_valor))
    parametros = {k: float(v) for k, v in campos.items() if not isinstance(v, str)}
    textuales = {k: v for k, v in campos.items() if isinstance(v, str)}
    if textuales:
        raise ErrorDeCaso(
            f"La componente '{clave}' tiene parámetros que no son números: {sorted(textuales)}"
        )
    return EspecificacionComponente(
        campo_valor=campo_valor,
        valor=valor,
        metodo=str(metodo) if metodo is not None else None,
        parametros=parametros,
    )


def _es_formato_viejo(datos: dict[str, Any]) -> bool:
    return "saneamiento" in datos and "casos" not in datos


ERROR_FORMATO_VIEJO = (
    "El archivo es de un caso suelto (formato viejo). Ahora un archivo describe la cuenca "
    "entera: datos compartidos, estados pre y post, y los casos. "
    "Usá cuencas/ejemplo_apunte.toml de plantilla."
)


# --- TOML ------------------------------------------------------------------


def leer_toml(origen: Path | str | bytes) -> Cuenca:
    datos = tomllib.loads(_texto(origen))
    if _es_formato_viejo(datos):
        raise ErrorDeCaso(ERROR_FORMATO_VIEJO)
    crudo: dict[str, Any] = {k: datos[k] for k in CAMPOS_CUENCA if k in datos}
    crudo["componentes"] = {
        clave: campos
        for clave, campos in datos.items()
        if isinstance(campos, dict) and clave != "estados"
    }
    crudo["estados"] = {
        clave: {
            **{c: v for c, v in estado.items() if not isinstance(v, dict)},
            "componentes": {c: v for c, v in estado.items() if isinstance(v, dict)},
        }
        for clave, estado in datos.get("estados", {}).items()
    }
    crudo["casos"] = datos.get("casos", [])
    return desde_dict(crudo)


def escribir_toml(cuenca: Cuenca) -> str:
    crudo = a_dict(cuenca)
    lineas = [
        "# Balance hidrológico anual — una cuenca comparada en distintos casos.",
        f"# Unidades admitidas para el valor directo: {', '.join(UNIDADES_VALOR)}.",
        "# Una componente ausente vale 0. Valor directo o método, nunca los dos.",
        "",
        "# --- Cuenca: lo que no cambia entre casos ---",
        f"nombre = {_cadena(crudo['nombre'])}",
        f"area_km2 = {_numero(crudo['area_km2'])}",
        f'cierre = {_cadena(crudo["cierre"])}   # se despeja en todos los casos; "{SIN_CIERRE}" = mostrar residuo',
    ]
    _tablas_toml(lineas, "", crudo["componentes"])

    for clave, estado in crudo["estados"].items():
        lineas.extend(["", f"# --- Estado de urbanización {clave} ---", f"[estados.{clave}]"])
        for campo in CAMPOS_REPARTO:
            if campo in estado:
                lineas.append(f"{campo} = {_numero(estado[campo])}")
        _tablas_toml(lineas, f"estados.{clave}.", estado["componentes"])

    lineas.extend(["", "# --- Casos: cada uno elige su estado y su saneamiento ---"])
    for caso in crudo["casos"]:
        lineas.extend(["", "[[casos]]"])
        for campo in ("nombre", *CAMPOS_CASO):
            lineas.append(f"{campo} = {_cadena(caso[campo])}")
    return "\n".join(lineas) + "\n"


def _tablas_toml(lineas: list[str], prefijo: str, componentes: dict[str, dict[str, Any]]) -> None:
    for clave, campos in componentes.items():
        lineas.extend(["", f"[{prefijo}{clave}]"])
        for campo, valor in campos.items():
            if isinstance(valor, str):
                lineas.append(f"{campo} = {_cadena(valor)}")
            else:
                lineas.append(f"{campo} = {_numero(valor)}")


# --- CSV / Excel -----------------------------------------------------------


def leer_csv(origen: Path | str | bytes) -> Cuenca:
    filas = list(csv.DictReader(_texto(origen).splitlines()))
    if filas and "ambito" not in filas[0]:
        raise ErrorDeCaso(ERROR_FORMATO_VIEJO)
    return _desde_filas([tuple(f[c] or "" for c in COLUMNAS_CSV) for f in filas])


def leer_excel(ruta: Any) -> Cuenca:
    import pandas as pd

    tabla = pd.read_excel(ruta, dtype=str).fillna("")
    if "ambito" not in tabla.columns:
        raise ErrorDeCaso(ERROR_FORMATO_VIEJO)
    return _desde_filas(
        [tuple(str(f[c]) for c in COLUMNAS_CSV) for _, f in tabla.iterrows()]
    )


def _desde_filas(filas: list[tuple[str, ...]]) -> Cuenca:
    crudo: dict[str, Any] = {"componentes": {}, "estados": {}, "casos": []}
    casos: dict[str, dict[str, str]] = {}
    for ambito, elemento, campo, valor in filas:
        ambito, elemento, campo, valor = (s.strip() for s in (ambito, elemento, campo, valor))
        if not ambito or ambito.startswith("#"):
            continue
        if ambito == "caso":
            casos.setdefault(elemento, {"nombre": elemento})[campo] = valor
            continue
        if ambito == "cuenca":
            destino = crudo
        elif ambito in ESTADOS:
            destino = crudo["estados"].setdefault(ambito, {"componentes": {}})
        else:
            raise ErrorDeCaso(
                f"Ámbito desconocido en la planilla: '{ambito}'. Usá cuenca, pre, post o caso."
            )
        if elemento:
            destino["componentes"].setdefault(elemento, {})[campo] = _valor_csv(campo, valor)
        else:
            destino[campo] = valor if campo in ("nombre", "cierre") else float(valor)
    crudo["casos"] = list(casos.values())
    return desde_dict(crudo)


def _valor_csv(campo: str, valor: str) -> Any:
    if campo == "metodo":
        return valor
    return float(valor)


def escribir_csv(cuenca: Cuenca) -> str:
    crudo = a_dict(cuenca)
    filas: list[tuple[str, ...]] = [COLUMNAS_CSV]
    for campo in CAMPOS_CUENCA:
        filas.append(("cuenca", "", campo, str(crudo[campo])))
    filas.extend(_filas_componentes("cuenca", crudo["componentes"]))
    for clave, estado in crudo["estados"].items():
        for campo in CAMPOS_REPARTO:
            if campo in estado:
                filas.append((clave, "", campo, str(estado[campo])))
        filas.extend(_filas_componentes(clave, estado["componentes"]))
    for caso in crudo["casos"]:
        for campo in CAMPOS_CASO:
            filas.append(("caso", caso["nombre"], campo, caso[campo]))
    salida = io.StringIO()
    csv.writer(salida, lineterminator="\n").writerows(filas)  # comillas si un nombre lleva comas
    return salida.getvalue()


def _filas_componentes(ambito: str, componentes: dict[str, dict[str, Any]]) -> list[tuple[str, ...]]:
    return [
        (ambito, clave, campo, str(valor))
        for clave, campos in componentes.items()
        for campo, valor in campos.items()
    ]


def leer(ruta: Path | str) -> Cuenca:
    """Lee una cuenca reconociendo el formato por la extensión."""
    ruta = Path(ruta)
    match ruta.suffix.lower():
        case ".toml":
            return leer_toml(ruta)
        case ".csv":
            return leer_csv(ruta)
        case ".xlsx" | ".xlsm":
            return leer_excel(ruta)
        case otro:
            raise ErrorDeCaso(f"Formato no reconocido: '{otro}'. Usá .toml, .csv o .xlsx.")


def _texto(origen: Path | str | bytes) -> str:
    if isinstance(origen, bytes):
        return origen.decode("utf-8")
    ruta = Path(origen)
    if len(str(origen)) < 260 and ruta.exists():
        return ruta.read_text(encoding="utf-8")
    return str(origen)


def _cadena(texto: str) -> str:
    # Las cadenas básicas de TOML escapan igual que JSON
    return json.dumps(texto, ensure_ascii=False)


def _numero(valor: float) -> str:
    return str(int(valor)) if float(valor).is_integer() else str(valor)
