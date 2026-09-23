"""Visualizador del balance hidrológico anual de una cuenca urbana.

    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from balance import graficos
from balance.carga import escribir_csv, escribir_toml, leer, leer_csv, leer_excel, leer_toml
from balance.modelo import (
    CIERRES_POSIBLES,
    COMPONENTES,
    COMPONENTES_CUENCA,
    COMPONENTES_ESTADO,
    ESTADOS,
    POR_CLAVE,
    SANEAMIENTOS,
    UNIDADES_VALOR,
    Caso,
    Cuenca,
    ErrorDeCaso,
    EspecificacionComponente,
    EstadoUrbanizacion,
    Reparto,
    Resultado,
    resolver,
)
from balance.validacion import UMBRAL_RESIDUO_PCT, advertencias

CUENCA_DE_EJEMPLO = Path(__file__).parent / "cuencas" / "ejemplo_apunte.toml"

# Métodos ofrecidos para cada componente, con sus parámetros y valores por defecto.
METODOS: dict[str, dict[str, dict[str, float]]] = {
    "agua_potable": {"dotacion": {"dotacion_l_hab_dia": 300.0, "poblacion": 10000.0}},
    "evapotranspiracion": {"fraccion_precipitacion": {"fraccion": 0.40}},
    "escurrimiento_subsuperficial": {"fraccion_precipitacion": {"fraccion": 0.30}},
    "escurrimiento_subterraneo": {"fraccion_precipitacion": {"fraccion": 0.20}},
    "escurrimiento_superficial": {
        "coeficiente": {"coeficiente": 0.25},
        "coeficiente_ponderado": {
            "fraccion_impermeable": 0.35,
            "coeficiente_impermeable": 0.55,
            "coeficiente_permeable": 0.05,
        },
    },
}

NOMBRE_SANEAMIENTO = {
    "red": "Red cloacal",
    "pozos": "Pozos absorbentes",
    "ninguno": "Sin saneamiento",
}
NOMBRE_ESTADO = {"pre": "Pre-urbanización", "post": "Post-urbanización"}
SIN_CIERRE = "Ninguna (mostrar residuo)"

st.set_page_config(page_title="Balance hidrológico urbano", page_icon="💧", layout="wide")


# --- Estado ----------------------------------------------------------------

if "cuenca" not in st.session_state:
    st.session_state.cuenca = leer(CUENCA_DE_EJEMPLO)
    # Cambia con cada archivo cargado, para que los widgets tomen los datos nuevos
    st.session_state.version = 0
    st.session_state.archivo_cargado = None


def leer_subido(archivo) -> Cuenca:
    datos = archivo.getvalue()
    if archivo.name.endswith(".toml"):
        return leer_toml(datos)
    if archivo.name.endswith(".csv"):
        return leer_csv(datos)
    return leer_excel(archivo)


# --- Barra lateral ---------------------------------------------------------

with st.sidebar:
    st.header("Cuenca")
    subido = st.file_uploader(
        "Cargar cuenca", type=["toml", "csv", "xlsx"],
        help="Un archivo con la cuenca entera: datos compartidos, estados pre y post, y casos. "
        "En planilla: formato largo (ambito, elemento, campo, valor).",
    )
    # El archivo sigue en el uploader en cada recarga: solo se lee cuando cambia,
    # así no pisa lo que se editó en pantalla.
    if subido is not None and subido.file_id != st.session_state.archivo_cargado:
        try:
            st.session_state.cuenca = leer_subido(subido)
            st.session_state.version += 1
            st.session_state.archivo_cargado = subido.file_id
        except (ErrorDeCaso, ValueError) as error:
            st.error(f"{subido.name}: {error}")

    nombres = [c.nombre for c in st.session_state.cuenca.casos]
    if not nombres:
        st.warning("La cuenca no tiene casos.")
        st.stop()
    activo = st.selectbox("Caso en pantalla", nombres)

    modo = "oscuro" if st.toggle("Modo oscuro", value=False) else "claro"
    umbral = st.number_input(
        "Umbral de residuo (%)", min_value=0.1, max_value=50.0,
        value=UMBRAL_RESIDUO_PCT, step=0.5,
        help="Por encima de este residuo, el balance se marca como no cerrado.",
    )
    st.caption("La cuenca de ejemplo trae los valores del esquema del apunte.")


# --- Edición ---------------------------------------------------------------


def clave_widget(*partes: str) -> str:
    return "-".join((str(st.session_state.version), *partes))


def editar_cuenca(cuenca: Cuenca) -> Cuenca:
    """Widgets para tocar la cuenca entera. Devuelve la cuenca editada."""
    datos, pre, post, casos = st.tabs(
        ["Cuenca (datos compartidos)", NOMBRE_ESTADO["pre"], NOMBRE_ESTADO["post"], "Casos"]
    )

    with datos:
        st.caption("Lo mismo en todos los casos: así se comparan estados de urbanización, "
                   "no cuencas distintas.")
        columnas = st.columns([2, 1, 2])
        nombre = columnas[0].text_input("Nombre de la cuenca", cuenca.nombre,
                                        key=clave_widget("nombre"))
        area = columnas[1].number_input(
            "Área (km²)", min_value=0.001, value=float(cuenca.area_km2), step=0.5,
            key=clave_widget("area"),
        )
        opciones_cierre = [SIN_CIERRE, *CIERRES_POSIBLES]
        cierre = columnas[2].selectbox(
            "Componente de cierre (la misma en todos los casos)", opciones_cierre,
            index=opciones_cierre.index(cuenca.cierre or SIN_CIERRE),
            format_func=lambda c: c if c == SIN_CIERRE else POR_CLAVE[c].etiqueta,
            key=clave_widget("cierre"),
        )
        cierre = None if cierre == SIN_CIERRE else cierre
        componentes = editar_componentes("cuenca", COMPONENTES_CUENCA, cuenca.componentes, None)

    estados = {}
    for pestana, clave in ((pre, "pre"), (post, "post")):
        with pestana:
            estados[clave] = editar_estado(cuenca.estados[clave], cierre)

    with casos:
        editados = [editar_caso(i, caso) for i, caso in enumerate(cuenca.casos)]

    return Cuenca(
        nombre=nombre, area_km2=area, componentes=componentes, cierre=cierre,
        estados=estados, casos=editados,
    )


def editar_estado(estado: EstadoUrbanizacion, cierre: str | None) -> EstadoUrbanizacion:
    clave = estado.clave
    st.caption("Compartido por todos los casos en este estado.")
    reparto = None
    if clave == "post":
        actual = estado.reparto or Reparto()
        st.markdown("**Reparto de la provisión de agua potable** (igual con red y con pozos)")
        columnas = st.columns(3)
        perdidas = columnas[0].number_input(
            "Pérdidas de red (fracción)", min_value=0.0, max_value=1.0,
            value=float(actual.fraccion_perdidas_red), step=0.01,
            key=clave_widget(clave, "perdidas"),
            help="Se fugan de los caños, se infiltran y salen por el escurrimiento "
            "subsuperficial. Tucci y Genz: entre 0.10 y 0.50.",
        )
        efluente = columnas[1].number_input(
            "Efluente cloacal (fracción)", min_value=0.0, max_value=1.0,
            value=float(actual.fraccion_efluente_cloacal), step=0.01,
            key=clave_widget(clave, "efluente"),
            help="Con red cloacal sale por la planta; con pozos absorbentes se infiltra "
            "y sale por el escurrimiento subsuperficial.",
        )
        columnas[2].metric(
            "Uso exterior (lo que queda)", f"{1 - perdidas - efluente:.3f}",
            help="Riego, limpieza, recreación. No se reparte: queda dentro de la ET.",
        )
        reparto = Reparto(fraccion_perdidas_red=perdidas, fraccion_efluente_cloacal=efluente)
        st.divider()
    componentes = editar_componentes(clave, COMPONENTES_ESTADO, estado.componentes, cierre)
    return EstadoUrbanizacion(clave=clave, componentes=componentes, reparto=reparto)


def editar_caso(indice: int, caso: Caso) -> Caso:
    columnas = st.columns([2, 1, 1])
    nombre = columnas[0].text_input(
        "Nombre del caso", caso.nombre, key=clave_widget("caso", str(indice), "nombre")
    )
    estado = columnas[1].selectbox(
        "Estado de urbanización", ESTADOS, index=ESTADOS.index(caso.estado),
        format_func=lambda e: NOMBRE_ESTADO[e], key=clave_widget("caso", str(indice), "estado"),
    )
    if estado == "pre":
        columnas[2].selectbox("Saneamiento", ["ninguno"], format_func=lambda s: NOMBRE_SANEAMIENTO[s],
                              disabled=True, key=clave_widget("caso", str(indice), "san-pre"))
        saneamiento = "ninguno"
    else:
        saneamiento = columnas[2].selectbox(
            "Saneamiento", SANEAMIENTOS, index=SANEAMIENTOS.index(caso.saneamiento),
            format_func=lambda s: NOMBRE_SANEAMIENTO[s],
            key=clave_widget("caso", str(indice), "san"),
        )
    return Caso(nombre=nombre, estado=estado, saneamiento=saneamiento)


def editar_componentes(
    ambito: str,
    claves: tuple[str, ...],
    actuales: dict[str, EspecificacionComponente],
    cierre: str | None,
) -> dict[str, EspecificacionComponente]:
    componentes: dict[str, EspecificacionComponente] = {}
    for clave in claves:
        definicion = POR_CLAVE[clave]
        if clave == cierre:
            st.caption(f"**{definicion.etiqueta}**: es la componente de cierre, "
                       "se despeja del balance.")
            continue
        esp = actuales.get(clave)
        metodos = METODOS.get(clave, {})
        opciones = ["Ausente (0)", "Valor directo", *(f"Método: {m}" for m in metodos)]
        if esp is None:
            actual = "Ausente (0)"
        elif esp.metodo:
            actual = f"Método: {esp.metodo}"
        else:
            actual = "Valor directo"

        with st.expander(definicion.etiqueta, expanded=False):
            fila = st.columns([2, 3])
            eleccion = fila[0].radio(
                "Cómo se obtiene", opciones, index=opciones.index(actual),
                key=clave_widget(ambito, clave, "modo"),
            )
            with fila[1]:
                nueva = _widgets_componente(ambito, clave, eleccion, esp, metodos)
            if clave == "escurrimiento_subsuperficial":
                st.caption("Parte base, solo de la lluvia. En cada caso se le suma lo que "
                           "se infiltra de la provisión (pérdidas y pozos absorbentes).")
        if nueva is not None:
            componentes[clave] = nueva
    return componentes


def _widgets_componente(ambito, clave, eleccion, esp, metodos) -> EspecificacionComponente | None:
    if eleccion == "Ausente (0)":
        st.caption("La componente no interviene: vale 0.")
        return None

    if eleccion == "Valor directo":
        unidad = st.selectbox(
            "Unidad", UNIDADES_VALOR,
            index=UNIDADES_VALOR.index(esp.campo_valor) if esp and esp.campo_valor else 0,
            key=clave_widget(ambito, clave, "unidad"),
        )
        valor = st.number_input(
            "Valor", value=float(esp.valor) if esp and esp.valor is not None else 0.0,
            step=1.0, key=clave_widget(ambito, clave, "valor"),
        )
        return EspecificacionComponente(campo_valor=unidad, valor=valor)

    metodo = eleccion.removeprefix("Método: ")
    parametros = {}
    for parametro, defecto in metodos[metodo].items():
        actual = esp.parametros.get(parametro, defecto) if esp and esp.metodo == metodo else defecto
        parametros[parametro] = st.number_input(
            parametro.replace("_", " "), value=float(actual),
            step=0.01 if parametro.startswith(("fraccion", "coeficiente")) else 1.0,
            key=clave_widget(ambito, clave, parametro),
        )
    return EspecificacionComponente(metodo=metodo, parametros=parametros)


# --- Tablas ----------------------------------------------------------------


def tabla_componentes(resultado: Resultado) -> pd.DataFrame:
    filas = []
    for definicion in COMPONENTES:
        valor = resultado.valores[definicion.clave]
        filas.append(
            {
                "Componente": graficos.etiqueta(definicion.clave, resultado, salto=" "),
                "Tipo": definicion.signo.capitalize(),
                "mm/año": round(valor, 1),
                "hm³/año": round(valor / 1000 * resultado.area_km2 * 1e6 / 1e6, 3),
                "% de entradas": round(100 * valor / resultado.total_entradas, 1)
                if resultado.total_entradas
                else 0.0,
            }
        )
    return pd.DataFrame(filas)


def tabla_diferencias(base: Resultado, comparado: Resultado) -> pd.DataFrame:
    filas = []
    for definicion in COMPONENTES:
        a = base.valores[definicion.clave]
        b = comparado.valores[definicion.clave]
        filas.append(
            {
                "Componente": definicion.etiqueta,
                f"{base.caso.nombre} (mm)": round(a, 1),
                f"{comparado.caso.nombre} (mm)": round(b, 1),
                "Diferencia (mm)": round(b - a, 1),
                "Diferencia (%)": round(100 * (b - a) / a, 1) if a else None,
            }
        )
    return pd.DataFrame(filas)


# --- Cuerpo ----------------------------------------------------------------

st.title("💧 Balance hidrológico anual")

with st.expander("Datos de la cuenca, sus estados y sus casos", expanded=False):
    try:
        editada = editar_cuenca(st.session_state.cuenca)
    except ErrorDeCaso as error:
        st.error(f"Los datos no se pueden calcular: {error}")
        st.stop()
st.session_state.cuenca = editada

# El nombre del caso puede haber cambiado en el editor: se sigue por su posición
indice_activo = nombres.index(activo)
resultados = []
for caso in editada.casos:
    try:
        resultados.append(resolver(editada, caso))
    except ErrorDeCaso as error:
        st.warning(f"«{caso.nombre}» quedó fuera de los gráficos: {error}")
try:
    resultado = resolver(editada, editada.casos[indice_activo])
except ErrorDeCaso as error:
    st.error(f"El caso no se puede calcular: {error}")
    st.stop()

for aviso in advertencias(resultado, umbral):
    st.warning(aviso)

marcadores = st.columns(4)
marcadores[0].metric("Entradas", f"{resultado.total_entradas:.0f} mm/año")
marcadores[1].metric("Salidas", f"{resultado.total_salidas:.0f} mm/año")
marcadores[2].metric("ΔS humedad del suelo", f"{resultado.variacion_almacenamiento:.0f} mm/año")
if resultado.clave_cierre:
    marcadores[3].metric(
        "Cierre",
        f"{resultado.valores[resultado.clave_cierre]:.0f} mm/año",
        help=f"Despejado por {POR_CLAVE[resultado.clave_cierre].etiqueta.lower()}.",
    )
else:
    marcadores[3].metric(
        "Residuo", f"{resultado.residuo_mm:.1f} mm/año", f"{resultado.residuo_pct:.1f} %"
    )

esquema, barras, comparacion, datos = st.tabs(
    ["Esquema y flujos", "Barras", "Comparación", "Datos"]
)

with esquema:
    columna_esquema, columna_sankey = st.columns(2)
    figura = graficos.esquema(resultado, modo)
    ancho, alto = figura.get_size_inches()
    # Ancho que da el alto común; si no entra en la columna, se achica entero
    columna_esquema.image(
        graficos.png(figura), width=round(graficos.ALTO_FLUJOS * ancho / alto)
    )
    columna_sankey.plotly_chart(graficos.sankey(resultado, modo), width="stretch")

with barras:
    st.plotly_chart(graficos.barras_comparativas(resultados, modo), width="stretch")
    st.plotly_chart(graficos.barras_apiladas(resultados, modo), width="stretch")

with comparacion:
    if len(resultados) < 2:
        st.info("Hace falta más de un caso para comparar.")
    else:
        nombres_resueltos = [r.caso.nombre for r in resultados]
        columnas = st.columns(2)
        base = columnas[0].selectbox("Caso base", nombres_resueltos, index=0)
        contra = columnas[1].selectbox(
            "Caso comparado", nombres_resueltos, index=min(1, len(nombres_resueltos) - 1)
        )
        por_nombre = {r.caso.nombre: r for r in resultados}
        st.dataframe(
            tabla_diferencias(por_nombre[base], por_nombre[contra]),
            width="stretch", hide_index=True,
        )

with datos:
    st.dataframe(tabla_componentes(resultado), width="stretch", hide_index=True)
    internos = {
        "perdidas_red": "pérdidas de red",
        "vertido_pozos": "vertido a pozos absorbentes",
    }
    if resultado.flujos_internos:
        st.caption(
            "Se infiltran y salen por el escurrimiento subsuperficial (no son componentes "
            "del balance): "
            + ", ".join(f"{internos[k]} {v:.1f} mm/año"
                        for k, v in resultado.flujos_internos.items())
        )
    st.subheader("Descargar la cuenca")
    archivo = editada.nombre.lower().replace(" ", "_")
    descargas = st.columns(2)
    descargas[0].download_button(
        "Descargar TOML", escribir_toml(editada), f"{archivo}.toml", "text/plain"
    )
    descargas[1].download_button(
        "Descargar CSV", escribir_csv(editada), f"{archivo}.csv", "text/csv"
    )
