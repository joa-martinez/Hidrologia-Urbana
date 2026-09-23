"""Gráficos del balance: barras y Sankey en plotly, esquema tipo apunte en matplotlib.

Todo en mm/año. Los colores salen de una paleta categórica validada para daltonismo
y se asignan en orden fijo, nunca cíclico.
"""

from __future__ import annotations

import io
from typing import Literal, Sequence

import plotly.graph_objects as go
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from matplotlib.transforms import Bbox

from .modelo import COMPONENTES, POR_CLAVE, Resultado

Modo = Literal["claro", "oscuro"]

# Paleta categórica (slots 1-8) en los dos modos.
SERIES = {
    "claro": ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"),
    "oscuro": ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
}
SUPERFICIE = {"claro": "#fcfcfb", "oscuro": "#1a1a19"}
TEXTO = {"claro": "#0b0b0b", "oscuro": "#ffffff"}
TEXTO_SUAVE = {"claro": "#52514e", "oscuro": "#c3c2b7"}
GRILLA = {"claro": "#e6e5e1", "oscuro": "#343431"}
# El almacenamiento no es un flujo: va en gris neutro, fuera de la paleta de series.
NEUTRO = {"claro": "#9b9a94", "oscuro": "#6f6e69"}
# Alto en píxeles del esquema y el Sankey, que van lado a lado en la app.
ALTO_FLUJOS = 420

# Color fijo por componente: la identidad no cambia si se filtran casos.
_ORDEN_COLOR = {
    "precipitacion": 0,
    "agua_potable": 1,
    "aporte_aguas_arriba": 2,
    "evapotranspiracion": 3,
    "escurrimiento_superficial": 4,
    "escurrimiento_subsuperficial": 5,
    "escurrimiento_subterraneo": 6,
    "descarga_planta": 7,
}


def color_componente(clave: str, modo: Modo = "claro") -> str:
    if clave == "almacenamiento_humedad":
        return NEUTRO[modo]
    return SERIES[modo][_ORDEN_COLOR[clave]]


def etiqueta(clave: str, resultado: Resultado, corta: bool = False, salto: str = "\n") -> str:
    """Etiqueta de la componente, aclarando cuando el subsuperficial trae agua de los pozos."""
    definicion = POR_CLAVE[clave]
    texto = definicion.corta if corta else definicion.etiqueta
    if clave == "escurrimiento_subsuperficial" and _de_pozos(resultado):
        texto += f"{salto}(en parte por pozos absorbentes)"
    return texto


def _de_pozos(resultado: Resultado) -> float:
    return resultado.flujos_internos.get("vertido_pozos", 0.0)


def _nota_pozos(clave: str, resultado: Resultado) -> str:
    """Para los hover: cuánto del subsuperficial viene de los pozos absorbentes."""
    pozos = _de_pozos(resultado)
    if clave != "escurrimiento_subsuperficial" or not pozos:
        return ""
    return f"<br>{pozos:.1f} mm/año de pozos absorbentes"


def _maquillar(fig: go.Figure, modo: Modo, titulo: str, leyenda: str = "arriba") -> go.Figure:
    fig.update_layout(
        title=titulo,
        template="plotly_white" if modo == "claro" else "plotly_dark",
        paper_bgcolor=SUPERFICIE[modo],
        plot_bgcolor=SUPERFICIE[modo],
        font=dict(color=TEXTO[modo], size=13),
        margin=dict(l=10, r=10, t=56, b=10 if leyenda == "arriba" else 20),
        legend=(
            dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None)
            if leyenda == "arriba"
            else dict(orientation="h", yanchor="top", y=-0.16, x=0, title=None)
        ),
        hoverlabel=dict(font_size=13),
        bargap=0.28,
        bargroupgap=0.06,
    )
    fig.update_yaxes(
        title="mm/año", gridcolor=GRILLA[modo], zerolinecolor=GRILLA[modo],
        title_font_color=TEXTO_SUAVE[modo], tickfont_color=TEXTO_SUAVE[modo],
    )
    fig.update_xaxes(
        showgrid=False, tickfont_color=TEXTO_SUAVE[modo], title_font_color=TEXTO_SUAVE[modo]
    )
    return fig


def barras_comparativas(resultados: Sequence[Resultado], modo: Modo = "claro") -> go.Figure:
    """Componentes en el eje X, una barra por caso. Muestra qué cambia entre casos."""
    # El eje es compartido: si algún caso tiene pozos, la aclaración va en el eje
    con_pozos = next((r for r in resultados if _de_pozos(r)), None)
    etiquetas = [
        etiqueta(d.clave, con_pozos, corta=True, salto="<br>") if con_pozos else d.corta
        for d in COMPONENTES
    ]
    fig = go.Figure()
    for i, resultado in enumerate(resultados):
        fig.add_bar(
            name=resultado.caso.nombre,
            x=etiquetas,
            y=[resultado.valores[d.clave] for d in COMPONENTES],
            customdata=[_nota_pozos(d.clave, resultado) for d in COMPONENTES],
            marker_color=SERIES[modo][i % 3],  # casos: slots 1-3, validados para todos los pares
            marker_line=dict(width=2, color=SUPERFICIE[modo]),
            hovertemplate="<b>%{x}</b><br>%{fullData.name}<br>%{y:.1f} mm/año"
            "%{customdata}<extra></extra>",
        )
    fig.update_layout(barmode="group")
    return _maquillar(fig, modo, "Componentes del balance, por caso")


def barras_apiladas(resultados: Sequence[Resultado], modo: Modo = "claro") -> go.Figure:
    """Entradas y salidas de cada caso, apiladas: se ve el cierre del balance."""
    ejes = []
    for resultado in resultados:
        ejes.extend([(resultado.caso.nombre, "Entradas"), (resultado.caso.nombre, "Salidas + ΔS")])
    x = [[e[0] for e in ejes], [e[1] for e in ejes]]

    con_pozos = next((r for r in resultados if _de_pozos(r)), None)
    fig = go.Figure()
    for definicion in COMPONENTES:
        lado = "Entradas" if definicion.signo == "entrada" else "Salidas + ΔS"
        alturas: list[float] = []
        notas: list[str] = []
        for resultado in resultados:
            valor = resultado.valores[definicion.clave]
            alturas.extend([valor if lado == "Entradas" else 0, valor if lado != "Entradas" else 0])
            notas.extend([_nota_pozos(definicion.clave, resultado)] * 2)
        if not any(alturas):
            continue
        fig.add_bar(
            name=etiqueta(definicion.clave, con_pozos, salto=" ") if con_pozos else definicion.etiqueta,
            x=x,
            y=alturas,
            customdata=notas,
            marker_color=color_componente(definicion.clave, modo),
            marker_line=dict(width=2, color=SUPERFICIE[modo]),  # 2px de separación entre tramos
            hovertemplate="<b>%{fullData.name}</b><br>%{y:.1f} mm/año%{customdata}<extra></extra>",
        )
    fig.update_layout(barmode="stack")
    return _maquillar(fig, modo, "Cierre del balance: entradas contra salidas", leyenda="abajo")


def sankey(resultado: Resultado, modo: Modo = "claro") -> go.Figure:
    """Diagrama de flujo del caso, con el ancho de cada banda proporcional a los mm."""
    valores = resultado.valores
    nodos = ["Cuenca"]
    colores_nodo = [TEXTO_SUAVE[modo]]
    indices = {"Cuenca": 0}

    def nodo(nombre: str, color: str) -> int:
        if nombre not in indices:
            indices[nombre] = len(nodos)
            nodos.append(nombre)
            colores_nodo.append(color)
        return indices[nombre]

    fuentes: list[int] = []
    destinos: list[int] = []
    magnitudes: list[float] = []
    colores: list[str] = []

    for definicion in COMPONENTES:
        valor = valores[definicion.clave]
        if valor <= 0 or definicion.signo == "almacenamiento":
            continue
        propio = nodo(
            etiqueta(definicion.clave, resultado, salto=" "),
            color_componente(definicion.clave, modo),
        )
        fuentes.append(propio if definicion.signo == "entrada" else 0)
        destinos.append(0 if definicion.signo == "entrada" else propio)
        magnitudes.append(valor)
        colores.append(color_componente(definicion.clave, modo) + "99")

    almacenamiento = valores["almacenamiento_humedad"]
    if almacenamiento > 0:
        fuentes.append(0)
        destinos.append(nodo("Almacenamiento en humedad del suelo", NEUTRO[modo]))
        magnitudes.append(almacenamiento)
        colores.append(NEUTRO[modo] + "99")

    fig = go.Figure(
        go.Sankey(
            arrangement="snap",
            node=dict(
                label=nodos,
                pad=18,
                thickness=16,
                color=colores_nodo,
                line=dict(width=0),
                hovertemplate="%{label}<br>%{value:.1f} mm/año<extra></extra>",
            ),
            link=dict(
                source=fuentes, target=destinos, value=magnitudes, color=colores,
                hovertemplate="%{source.label} → %{target.label}<br>%{value:.1f} mm/año<extra></extra>",
            ),
        )
    )
    fig.update_layout(
        title=f"Flujos del caso: {resultado.caso.nombre}",
        paper_bgcolor=SUPERFICIE[modo],
        font=dict(color=TEXTO[modo], size=13),
        margin=dict(l=10, r=10, t=56, b=10),
        height=ALTO_FLUJOS,
    )
    return fig


# --- Esquema tipo apunte ---------------------------------------------------

# Ramas hacia arriba (entradas y evaporación) y hacia abajo (a cuerpo receptor),
# en el orden en que aparecen en la figura del Capítulo 2.
_RAMAS_ARRIBA = (
    ("agua_potable", "Provisión de\nagua potable"),
    ("precipitacion", "Precipitación"),
    ("evapotranspiracion", "Evapotrans-\npiración"),
    ("aporte_aguas_arriba", "Filtración desde\naguas arriba"),
)
_RAMAS_ABAJO = (
    ("descarga_planta", "Descarga planta\ntratamiento cloacal"),
    ("escurrimiento_superficial", "Escurrimiento\nsuperficial"),
    ("escurrimiento_subsuperficial", "Escurrimiento\nsubsuperficial"),
    ("escurrimiento_subterraneo", "Escurrimiento\nsubterráneo"),
)


def esquema(resultado: Resultado, modo: Modo = "claro") -> Figure:
    """Reproduce el esquema del apunte: ancho de cada rama proporcional a los mm.

    El tamaño de la figura sale de lo dibujado, así ningún rótulo queda afuera.
    """
    valores = resultado.valores
    cuerpo = "#c9c8c3" if modo == "claro" else "#4a4a46"
    tinta = TEXTO[modo]

    maximo = max(max(valores.values()), 1.0)
    ancho = lambda v: 0.3 + 1.5 * (v / maximo)  # noqa: E731
    SEPARACION = 2.2  # el texto de las etiquetas es más ancho que las ramas

    # Escala fija desde el principio: así el texto mide lo mismo en unidades de dibujo
    # antes y después de encuadrar, y se puede medir para acomodar el resto.
    fig = Figure(figsize=(1, 1), facecolor=SUPERFICIE[modo])
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_facecolor(SUPERFICIE[modo])
    _escalar(fig, ax, (0.0, 1.0, 0.0, 1.0))

    def repartir(ramas) -> dict[str, tuple[float, float]]:
        """Una componente nula no dibuja rama: así se ve que ese camino no existe."""
        posiciones, x = {}, 0.0
        for clave, _ in ramas:
            if valores[clave] <= 0:
                continue
            w = ancho(valores[clave])
            posiciones[clave] = (x + w / 2, w)
            x += w + SEPARACION
        return posiciones

    def extension(posiciones: dict[str, tuple[float, float]]) -> float:
        return max((c + w / 2 for c, w in posiciones.values()), default=0.0)

    # El almacenamiento va escrito dentro del tronco: el tronco tiene que alojarlo
    rotulo_almacenamiento = ax.text(
        0, 0, f"ΔS humedad del suelo: {valores['almacenamiento_humedad']:.0f} mm",
        ha="center", va="center", color=tinta, fontsize=9.5, zorder=3,
    )
    largo_rotulo = _ancho_en_datos(rotulo_almacenamiento, ax) + 0.6

    # El tronco cubre las ramas de arriba y las de abajo, y cada grupo va centrado sobre él
    arriba, abajo = repartir(_RAMAS_ARRIBA), repartir(_RAMAS_ABAJO)
    izq = 0.0
    der = max(extension(arriba), extension(abajo), largo_rotulo)
    arriba = _centrar(arriba, der)
    abajo = _centrar(abajo, der)

    ax.add_patch(Polygon([(izq, -0.35), (der, -0.35), (der, 0.35), (izq, 0.35)],
                         facecolor=cuerpo, edgecolor="none"))
    rotulo_almacenamiento.set_x((izq + der) / 2)

    for i, (clave, rotulo) in enumerate(c for c in _RAMAS_ARRIBA if c[0] in arriba):
        centro, w = arriba[clave]
        valor = valores[clave]
        entrada = POR_CLAVE[clave].signo == "entrada"
        alto = 2.6 if i % 2 == 0 else 3.6  # dos alturas, para que los textos no se pisen
        # las entradas apuntan al tronco; la evaporación, al extremo libre
        ax.add_patch(_rama(centro, w, 0.0, alto, punta_en="base" if entrada else "extremo", color=cuerpo))
        ax.text(centro, alto + 0.22, f"{valor:.0f}", ha="center", va="bottom",
                color=tinta, fontsize=12, fontweight="bold")
        ax.text(centro, alto + 0.75, rotulo, ha="center", va="bottom", color=tinta, fontsize=10.5)

    for i, (clave, rotulo) in enumerate(c for c in _RAMAS_ABAJO if c[0] in abajo):
        centro, w = abajo[clave]
        if clave == "escurrimiento_subsuperficial" and _de_pozos(resultado):
            rotulo += f"\n(en parte por pozos\nabsorbentes: {_de_pozos(resultado):.0f})"
        valor = valores[clave]
        alto = -2.4 if i % 2 == 0 else -3.4
        ax.add_patch(_rama(centro, w, 0.0, alto, punta_en="extremo", color=cuerpo))
        ancho_suelo = max(0.9, w * 0.9)
        ax.plot([centro - ancho_suelo, centro + ancho_suelo], [alto - 0.1, alto - 0.1],
                color=tinta, lw=1.6)
        for k in range(5):
            x0 = centro - ancho_suelo + k * (2 * ancho_suelo - 0.25) / 4
            ax.plot([x0, x0 + 0.22], [alto - 0.1, alto - 0.38], color=tinta, lw=1.1)
        ax.text(centro, alto + 0.42, f"{valor:.0f}", ha="center", va="top",
                color=tinta, fontsize=12, fontweight="bold")
        ax.text(centro, alto - 0.62, rotulo, ha="center", va="top", color=tinta, fontsize=10.5)

    pie = f"{resultado.caso.nombre} — valores en mm/año"
    if resultado.clave_cierre:
        pie += f" · cierre por {POR_CLAVE[resultado.clave_cierre].etiqueta.lower()}"
    else:
        pie += f" · residuo {resultado.residuo_mm:.1f} mm ({resultado.residuo_pct:.1f} %)"
    ax.set_title(pie, color=tinta, fontsize=12, pad=8)

    ax.axis("off")
    _encuadrar(fig, ax)
    return fig


# Pulgadas por unidad de dibujo del esquema: fija el tamaño del texto respecto de las ramas.
_ESCALA = 0.42
_MARGEN = 0.3  # en unidades de dibujo, alrededor de todo lo dibujado
_ALTO_TITULO = 0.45  # en pulgadas, franja reservada arriba para el título


def _escalar(fig: Figure, ax, limites: tuple[float, float, float, float]) -> None:
    """Pone los límites y ajusta la figura para que una unidad mida siempre _ESCALA pulgadas."""
    x0, x1, y0, y1 = limites
    ancho, alto = (x1 - x0) * _ESCALA, (y1 - y0) * _ESCALA
    fig.set_size_inches(ancho, alto + _ALTO_TITULO)
    ax.set_position((0, 0, 1, alto / (alto + _ALTO_TITULO)))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def _ancho_en_datos(texto, ax) -> float:
    renderer = ax.figure.canvas.get_renderer()
    return texto.get_window_extent(renderer).width / ax.figure.dpi / _ESCALA


def _centrar(posiciones: dict[str, tuple[float, float]], largo: float) -> dict[str, tuple[float, float]]:
    ocupado = max((c + w / 2 for c, w in posiciones.values()), default=0.0)
    corrimiento = (largo - ocupado) / 2
    return {k: (c + corrimiento, w) for k, (c, w) in posiciones.items()}


def _encuadrar(fig: Figure, ax) -> None:
    """Ajusta límites y tamaño de la figura a todo lo dibujado, más un margen."""
    renderer = fig.canvas.get_renderer()
    a_datos = ax.transData.inverted()
    cajas = [a.get_window_extent(renderer) for a in (*ax.patches, *ax.lines, *ax.texts)]
    caja = Bbox.union(cajas).transformed(a_datos)
    x0, x1 = caja.x0 - _MARGEN, caja.x1 + _MARGEN
    y0, y1 = caja.y0 - _MARGEN, caja.y1 + _MARGEN
    # El título no puede ser más ancho que la figura
    ancho_titulo = _ancho_en_datos(ax.title, ax) + 2 * _MARGEN
    if ancho_titulo > x1 - x0:
        sobra = (ancho_titulo - (x1 - x0)) / 2
        x0, x1 = x0 - sobra, x1 + sobra
    _escalar(fig, ax, (x0, x1, y0, y1))


def png(fig: Figure, dpi: int = 150) -> bytes:
    """La figura como PNG, tal cual su tamaño: el encuadre ya lo hizo esquema()."""
    salida = io.BytesIO()
    fig.savefig(salida, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    return salida.getvalue()


def _rama(centro: float, ancho: float, base: float, alto: float, punta_en: str, color: str) -> Polygon:
    """Una rama del esquema: un tallo con punta de flecha en uno de sus extremos."""
    mitad = ancho / 2
    largo = 0.55 if alto > base else -0.55  # la punta se mide hacia el tronco
    if punta_en == "base":
        vertices = [
            (centro - mitad, alto), (centro + mitad, alto),
            (centro + mitad, base + largo), (centro, base), (centro - mitad, base + largo),
        ]
    else:
        vertices = [
            (centro - mitad, base), (centro + mitad, base),
            (centro + mitad, alto - largo), (centro, alto), (centro - mitad, alto - largo),
        ]
    return Polygon(vertices, closed=True, facecolor=color, edgecolor="none")
