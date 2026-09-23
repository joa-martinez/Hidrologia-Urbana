"""Modelo del balance hidrológico anual de una cuenca urbana.

Vocabulario en CONTEXT.md. Unidad interna: mm/año.

Los datos se organizan en tres niveles (ver docs/adr/0002-cuenca-estado-caso.md):
la Cuenca tiene lo que no cambia entre Casos, el Estado de urbanización lo que
depende de cuánto se urbanizó, y el Caso solo elige su Saneamiento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SEGUNDOS_POR_ANIO = 365 * 24 * 3600

Signo = Literal["entrada", "salida", "almacenamiento"]


@dataclass(frozen=True)
class DefinicionComponente:
    clave: str
    etiqueta: str
    signo: Signo
    corta: str  # para ejes y tablas, donde la etiqueta completa no entra


# El orden es además el orden de resolución: una componente solo puede depender
# de las que están antes que ella.
COMPONENTES: tuple[DefinicionComponente, ...] = (
    DefinicionComponente("precipitacion", "Precipitación", "entrada", "Precipitación"),
    DefinicionComponente("agua_potable", "Provisión de agua potable", "entrada", "Agua potable"),
    DefinicionComponente(
        "aporte_aguas_arriba", "Aporte desde aguas arriba", "entrada", "Aporte aguas arriba"
    ),
    # La ET va junta (incluye la evaporación del sistema de agua potable y el uso
    # exterior) y suele ser la componente de cierre: es la más difícil de estimar.
    # Ecuación (2.8) del Cap. 2.
    DefinicionComponente("evapotranspiracion", "Evapotranspiración", "salida", "ET"),
    DefinicionComponente(
        "escurrimiento_superficial", "Escurrimiento superficial", "salida", "Escurr. superficial"
    ),
    DefinicionComponente(
        "escurrimiento_subsuperficial", "Escurrimiento subsuperficial", "salida", "Escurr. subsup."
    ),
    DefinicionComponente(
        "escurrimiento_subterraneo", "Escurrimiento subterráneo", "salida", "Escurr. subterráneo"
    ),
    # No se carga: sale del Reparto de la provisión cuando el Saneamiento es la red.
    DefinicionComponente("descarga_planta", "Descarga de planta cloacal", "salida", "Descarga cloacal"),
    DefinicionComponente(
        "almacenamiento_humedad", "Almacenamiento en humedad del suelo", "almacenamiento",
        "ΔS humedad",
    ),
)

POR_CLAVE = {d.clave: d for d in COMPONENTES}

# Qué componentes se cargan en cada nivel. La descarga de planta no se carga en ninguno.
COMPONENTES_CUENCA = ("precipitacion", "agua_potable", "aporte_aguas_arriba")
COMPONENTES_ESTADO = (
    "evapotranspiracion",
    "escurrimiento_superficial",
    "escurrimiento_subsuperficial",
    "escurrimiento_subterraneo",
    "almacenamiento_humedad",
)
# Solo se puede despejar algo que dependa del Estado: lo de la Cuenca es dato
# compartido y la descarga de planta sale del reparto.
CIERRES_POSIBLES = COMPONENTES_ESTADO

# Componentes de versiones anteriores del modelo, con el nombre nuevo o su reemplazo.
RENOMBRADAS = {
    "escurrimiento_directo": "escurrimiento_superficial",
    "evaporacion_sistema": "evapotranspiracion (ahora va todo junto en una sola componente)",
    "vertido_pozos": (
        "fraccion_efluente_cloacal del estado post (el vertido a pozos ya no se carga: "
        "sale del reparto de la provisión y va al escurrimiento subsuperficial)"
    ),
    "descarga_planta": (
        "fraccion_efluente_cloacal del estado post (la descarga de planta ya no se carga: "
        "sale del reparto de la provisión)"
    ),
}

Saneamiento = Literal["red", "pozos", "ninguno"]
SANEAMIENTOS: tuple[Saneamiento, ...] = ("red", "pozos", "ninguno")
Estado = Literal["pre", "post"]
ESTADOS: tuple[Estado, ...] = ("pre", "post")

# Sufijo de unidad admitido en el campo de valor directo -> factor a mm/año.
# El factor puede depender del área, así que se resuelve en tiempo de cálculo.
UNIDADES_VALOR = ("valor_mm", "valor_hm3", "valor_m3", "valor_l_s")


class ErrorDeCaso(ValueError):
    """Datos imposibles: el balance no se puede calcular."""


@dataclass
class EspecificacionComponente:
    """Cómo obtener el valor de una Componente: valor directo o método de cálculo."""

    campo_valor: str | None = None  # "valor_mm", "valor_hm3", ...
    valor: float | None = None
    metodo: str | None = None
    parametros: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.valor is not None and self.metodo is not None:
            raise ErrorDeCaso(
                "Una componente define un valor directo o un método de cálculo, nunca ambos."
            )


def _validar_claves(componentes: dict, admitidas: tuple[str, ...], donde: str) -> None:
    desconocidas = set(componentes) - set(admitidas)
    for vieja in sorted(desconocidas & set(RENOMBRADAS)):
        raise ErrorDeCaso(f"«{vieja}» ahora es «{RENOMBRADAS[vieja]}».")
    for clave in sorted(desconocidas & set(POR_CLAVE)):
        raise ErrorDeCaso(f"«{clave}» no se carga en {donde}.")
    if desconocidas:
        raise ErrorDeCaso(f"Componentes desconocidas en {donde}: {sorted(desconocidas)}")


@dataclass
class Reparto:
    """Reparto de la provisión: pérdidas, efluente cloacal y, lo que queda, uso exterior."""

    fraccion_perdidas_red: float = 0.0
    fraccion_efluente_cloacal: float = 0.0

    def __post_init__(self) -> None:
        for nombre, fraccion in (
            ("pérdidas de red", self.fraccion_perdidas_red),
            ("efluente cloacal", self.fraccion_efluente_cloacal),
        ):
            if not 0 <= fraccion <= 1:
                raise ErrorDeCaso(f"La fracción de {nombre} tiene que estar entre 0 y 1.")
        if self.fraccion_perdidas_red + self.fraccion_efluente_cloacal > 1 + 1e-9:
            raise ErrorDeCaso(
                "Las pérdidas de red más el efluente cloacal no pueden pasar de toda la "
                f"provisión: suman {self.fraccion_perdidas_red + self.fraccion_efluente_cloacal:.3f}."
            )

    @property
    def fraccion_uso_exterior(self) -> float:
        # Riego, limpieza, recreación: queda implícito dentro de la ET.
        return 1 - self.fraccion_perdidas_red - self.fraccion_efluente_cloacal


@dataclass
class EstadoUrbanizacion:
    """Lo que depende de cuánto se urbanizó la cuenca y no del saneamiento."""

    clave: Estado
    componentes: dict[str, EspecificacionComponente] = field(default_factory=dict)
    # Solo el estado Post tiene provisión de agua potable que repartir.
    reparto: Reparto | None = None

    def __post_init__(self) -> None:
        if self.clave not in ESTADOS:
            raise ErrorDeCaso(f"Estado de urbanización desconocido: '{self.clave}'. Usá pre o post.")
        _validar_claves(self.componentes, COMPONENTES_ESTADO, f"el estado {self.clave}")
        if self.clave == "pre" and self.reparto is not None:
            raise ErrorDeCaso("Antes de urbanizar no hay provisión de agua potable que repartir.")
        if self.clave == "post" and self.reparto is None:
            self.reparto = Reparto()


@dataclass
class Caso:
    """Un escenario de la Cuenca: su Estado de urbanización y su Saneamiento."""

    nombre: str
    estado: Estado
    saneamiento: Saneamiento = "ninguno"

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ErrorDeCaso(
                f"El caso «{self.nombre}» tiene un estado desconocido: '{self.estado}'."
            )
        if self.saneamiento not in SANEAMIENTOS:
            raise ErrorDeCaso(
                f"El caso «{self.nombre}» tiene un saneamiento desconocido: '{self.saneamiento}'."
            )
        if self.estado == "pre" and self.saneamiento != "ninguno":
            raise ErrorDeCaso(
                f"El caso «{self.nombre}» es pre-urbanización: no puede tener saneamiento."
            )


@dataclass
class Cuenca:
    """La cuenca que se compara: datos compartidos, sus dos estados y sus casos."""

    nombre: str
    area_km2: float
    componentes: dict[str, EspecificacionComponente] = field(default_factory=dict)
    # Una sola para todos los casos, así la incógnita absorbe el error en el mismo lugar.
    cierre: str | None = None
    estados: dict[str, EstadoUrbanizacion] = field(default_factory=dict)
    casos: list[Caso] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.area_km2 <= 0:
            raise ErrorDeCaso("El área de la cuenca debe ser mayor que cero.")
        _validar_claves(self.componentes, COMPONENTES_CUENCA, "la cuenca")
        if self.cierre is not None and self.cierre not in CIERRES_POSIBLES:
            raise ErrorDeCaso(
                f"«{self.cierre}» no puede ser la componente de cierre. "
                f"Opciones: {', '.join(CIERRES_POSIBLES)}."
            )
        for clave in ESTADOS:
            self.estados.setdefault(clave, EstadoUrbanizacion(clave))
        for clave, estado in self.estados.items():
            if clave != estado.clave:
                raise ErrorDeCaso(f"El estado guardado como '{clave}' dice ser '{estado.clave}'.")
            if self.cierre in estado.componentes:
                raise ErrorDeCaso(
                    f"«{POR_CLAVE[self.cierre].etiqueta}» es la componente de cierre: "
                    f"se despeja del balance y no se carga en el estado {clave}."
                )
        nombres = [c.nombre for c in self.casos]
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidos:
            raise ErrorDeCaso(f"Hay casos con el mismo nombre: {repetidos}")

    def caso(self, nombre: str) -> Caso:
        for caso in self.casos:
            if caso.nombre == nombre:
                return caso
        raise ErrorDeCaso(f"La cuenca no tiene un caso llamado «{nombre}».")


@dataclass
class Resultado:
    """Balance resuelto de un Caso, con todo en mm/año."""

    caso: Caso
    area_km2: float
    valores: dict[str, float]
    # Lo que se infiltra dentro de la cuenca y sale por el escurrimiento subsuperficial.
    flujos_internos: dict[str, float]
    clave_cierre: str | None
    residuo_mm: float
    reparto: Reparto | None = None

    @property
    def entradas(self) -> dict[str, float]:
        return {c: v for c, v in self.valores.items() if POR_CLAVE[c].signo == "entrada"}

    @property
    def salidas(self) -> dict[str, float]:
        return {c: v for c, v in self.valores.items() if POR_CLAVE[c].signo == "salida"}

    @property
    def total_entradas(self) -> float:
        return sum(self.entradas.values())

    @property
    def total_salidas(self) -> float:
        return sum(self.salidas.values())

    @property
    def variacion_almacenamiento(self) -> float:
        return self.valores.get("almacenamiento_humedad", 0.0)

    @property
    def residuo_pct(self) -> float:
        if self.total_entradas == 0:
            return 0.0
        return 100 * self.residuo_mm / self.total_entradas

    @property
    def efluente_cloacal(self) -> float:
        if self.reparto is None:
            return 0.0
        return self.reparto.fraccion_efluente_cloacal * self.valores["agua_potable"]


def a_mm(campo: str, valor: float, area_km2: float) -> float:
    """Convierte un valor directo a mm/año según el sufijo de unidad del campo."""
    area_m2 = area_km2 * 1e6
    match campo:
        case "valor_mm":
            return valor
        case "valor_hm3":
            return valor * 1e6 / area_m2 * 1000
        case "valor_m3":
            return valor / area_m2 * 1000
        case "valor_l_s":
            return valor * 1e-3 * SEGUNDOS_POR_ANIO / area_m2 * 1000
        case _:
            raise ErrorDeCaso(
                f"Unidad no reconocida: '{campo}'. Admitidas: {', '.join(UNIDADES_VALOR)}"
            )


def _parametro(esp: EspecificacionComponente, nombre: str, defecto: float | None = None) -> float:
    if nombre in esp.parametros:
        return float(esp.parametros[nombre])
    if defecto is None:
        raise ErrorDeCaso(f"El método '{esp.metodo}' necesita el parámetro '{nombre}'.")
    return defecto


def _aplicar_metodo(
    esp: EspecificacionComponente, area_km2: float, ya_calculadas: dict[str, float]
) -> float:
    match esp.metodo:
        case "dotacion":
            dotacion = _parametro(esp, "dotacion_l_hab_dia")
            poblacion = _parametro(esp, "poblacion")
            volumen_m3 = dotacion * poblacion * 365 / 1000
            return volumen_m3 / (area_km2 * 1e6) * 1000

        case "fraccion_precipitacion":
            fraccion = _parametro(esp, "fraccion")
            return fraccion * ya_calculadas.get("precipitacion", 0.0)

        case "coeficiente":
            return _parametro(esp, "coeficiente") * ya_calculadas.get("precipitacion", 0.0)

        case "coeficiente_ponderado":
            # C ponderado entre la parte impermeable de la cuenca y la permeable
            impermeable = _parametro(esp, "fraccion_impermeable")
            coef = impermeable * _parametro(esp, "coeficiente_impermeable") + (
                1 - impermeable
            ) * _parametro(esp, "coeficiente_permeable")
            return coef * ya_calculadas.get("precipitacion", 0.0)

        case _:
            raise ErrorDeCaso(f"Método de cálculo desconocido: '{esp.metodo}'.")


def resolver(cuenca: Cuenca, caso: Caso | str) -> Resultado:
    """Calcula todas las componentes de un caso de la cuenca y cierra (o mide) el balance."""
    if isinstance(caso, str):
        caso = cuenca.caso(caso)
    estado = cuenca.estados[caso.estado]
    especificaciones = {**cuenca.componentes, **estado.componentes}
    if caso.estado == "pre":
        # La dotación y la población son de la cuenca, pero antes de urbanizar no hay red.
        especificaciones.pop("agua_potable", None)

    valores: dict[str, float] = {}
    for definicion in COMPONENTES:
        clave = definicion.clave
        esp = especificaciones.get(clave)
        if esp is None or clave == cuenca.cierre:
            valores[clave] = 0.0  # una componente ausente vale 0; el cierre se despeja al final
        elif esp.valor is not None:
            valores[clave] = a_mm(esp.campo_valor or "valor_mm", esp.valor, cuenca.area_km2)
        elif esp.metodo is not None:
            valores[clave] = _aplicar_metodo(esp, cuenca.area_km2, valores)
        else:
            valores[clave] = 0.0

    # Reparto de la provisión. Las pérdidas y, con pozos, el efluente se infiltran y
    # salen por el escurrimiento subsuperficial; con red, el efluente sale por la planta.
    # El uso exterior no se asigna: queda dentro de la ET cuando es el cierre.
    internos: dict[str, float] = {}
    provision = valores["agua_potable"]
    reparto = estado.reparto
    if reparto is not None and provision:
        perdidas = reparto.fraccion_perdidas_red * provision
        efluente = reparto.fraccion_efluente_cloacal * provision
        if perdidas:
            internos["perdidas_red"] = perdidas
        if caso.saneamiento == "red":
            valores["descarga_planta"] = efluente
        elif caso.saneamiento == "pozos" and efluente:
            internos["vertido_pozos"] = efluente
    # Si el subsuperficial es el cierre, lo infiltrado ya queda contemplado al despejarlo.
    if cuenca.cierre != "escurrimiento_subsuperficial":
        valores["escurrimiento_subsuperficial"] += sum(internos.values())

    if cuenca.cierre is not None:
        despejado = _residuo(valores)
        if POR_CLAVE[cuenca.cierre].signo == "entrada":
            despejado = -despejado
        valores[cuenca.cierre] = despejado

    return Resultado(
        caso=caso,
        area_km2=cuenca.area_km2,
        valores=valores,
        flujos_internos=internos,
        clave_cierre=cuenca.cierre,
        residuo_mm=_residuo(valores),
        reparto=reparto,
    )


def resolver_todos(cuenca: Cuenca) -> list[Resultado]:
    return [resolver(cuenca, caso) for caso in cuenca.casos]


def _residuo(valores: dict[str, float]) -> float:
    """Entradas − salidas − variación de almacenamiento."""
    total = 0.0
    for definicion in COMPONENTES:
        valor = valores.get(definicion.clave, 0.0)
        total += valor if definicion.signo == "entrada" else -valor
    return total
