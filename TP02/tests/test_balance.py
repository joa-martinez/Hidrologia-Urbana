"""Tests del núcleo: conversiones, cierre, reparto de la provisión, y equivalencia entre TOML y CSV."""

from dataclasses import replace
from pathlib import Path

import pytest

from balance.carga import escribir_csv, escribir_toml, leer, leer_csv, leer_toml
from balance.modelo import (
    Caso,
    Cuenca,
    ErrorDeCaso,
    EspecificacionComponente,
    EstadoUrbanizacion,
    Reparto,
    a_mm,
    resolver,
    resolver_todos,
)
from balance.validacion import advertencias

EJEMPLO = Path(__file__).resolve().parent.parent / "cuencas" / "ejemplo_apunte.toml"
PRE = "Pre-urbanización"
RED = "Post-urbanización con red cloacal"
POZOS = "Post-urbanización con pozos absorbentes"


def mm(valor: float) -> EspecificacionComponente:
    return EspecificacionComponente(campo_valor="valor_mm", valor=valor)


@pytest.fixture
def cuenca() -> Cuenca:
    return leer(EJEMPLO)


def test_conversion_de_unidades_a_mm():
    # 1 hm³ sobre 1 km² son 1000 mm de lámina
    assert a_mm("valor_hm3", 1, area_km2=1.0) == pytest.approx(1000)
    assert a_mm("valor_m3", 1e6, area_km2=1.0) == pytest.approx(1000)
    assert a_mm("valor_mm", 743, area_km2=12.5) == 743
    # 1 L/s durante un año sobre 1 km² son 31.536 mm
    assert a_mm("valor_l_s", 1, area_km2=1.0) == pytest.approx(31.536)


def test_unidad_desconocida_es_error():
    with pytest.raises(ErrorDeCaso, match="Unidad no reconocida"):
        a_mm("valor_litros", 1, area_km2=1.0)


def test_el_caso_con_red_reproduce_el_esquema_del_apunte(cuenca):
    valores = resolver(cuenca, RED).valores
    assert valores["precipitacion"] == pytest.approx(743)
    assert valores["agua_potable"] == pytest.approx(529, abs=0.5)
    assert valores["descarga_planta"] == pytest.approx(456, abs=0.5)
    assert valores["escurrimiento_superficial"] == pytest.approx(168, abs=1.0)
    assert valores["escurrimiento_subsuperficial"] == pytest.approx(367, abs=2.0)
    # la ET junta: 312 de la cuenca + 73 del sistema de agua potable en el esquema
    assert valores["evapotranspiracion"] == pytest.approx(385, abs=2.0)


def test_los_datos_de_la_cuenca_son_los_mismos_en_todos_los_casos(cuenca):
    resultados = resolver_todos(cuenca)
    for clave in ("precipitacion", "aporte_aguas_arriba"):
        assert len({r.valores[clave] for r in resultados}) == 1
    # antes de urbanizar no hay red de agua potable, aunque la cuenca tenga dotación
    assert resolver(cuenca, PRE).valores["agua_potable"] == 0
    assert resolver(cuenca, RED).valores["agua_potable"] == resolver(cuenca, POZOS).valores[
        "agua_potable"
    ]


def test_la_componente_de_cierre_hace_cerrar_el_balance(cuenca):
    resultado = resolver(cuenca, PRE)
    assert resultado.clave_cierre == "evapotranspiracion"
    assert resultado.residuo_mm == pytest.approx(0, abs=1e-9)
    # entradas 851 − superficial 74.3 − subsuperficial 222.9 − subterráneo 148.6 − ΔS 3
    assert resultado.valores["evapotranspiracion"] == pytest.approx(402.2, abs=0.1)


def test_sin_componente_de_cierre_se_informa_el_residuo():
    cuenca = Cuenca(
        nombre="Con residuo",
        area_km2=1.0,
        componentes={"precipitacion": mm(1000)},
        estados={"pre": EstadoUrbanizacion("pre", {"evapotranspiracion": mm(400)})},
        casos=[Caso("Pre", "pre")],
    )
    resultado = resolver(cuenca, "Pre")
    assert resultado.clave_cierre is None
    assert resultado.residuo_mm == pytest.approx(600)
    assert resultado.residuo_pct == pytest.approx(60)
    assert any("no cierra" in aviso for aviso in advertencias(resultado))


def test_con_pozos_el_efluente_sale_por_los_pozos(cuenca):
    con_red = resolver(cuenca, RED)
    con_pozos = resolver(cuenca, POZOS)

    efluente = con_red.valores["descarga_planta"]
    assert efluente == pytest.approx(0.862 * con_red.valores["agua_potable"])
    assert con_pozos.valores["descarga_planta"] == 0
    assert con_red.valores["vertido_pozos"] == 0
    assert con_pozos.valores["vertido_pozos"] == pytest.approx(efluente)
    # sale por su propia salida: ningún escurrimiento cambia
    for clave in ("escurrimiento_subsuperficial", "escurrimiento_subterraneo"):
        assert con_pozos.valores[clave] == pytest.approx(con_red.valores[clave])
    # el mismo efluente cambia de camino: la ET no se entera
    assert con_pozos.valores["evapotranspiracion"] == pytest.approx(
        con_red.valores["evapotranspiracion"]
    )
    assert not advertencias(con_red) and not advertencias(con_pozos)


def test_las_perdidas_de_red_se_infiltran_y_salen_por_el_subsuperficial(cuenca):
    sin_perdidas = resolver(cuenca, RED)
    cuenca.estados["post"].reparto = Reparto(
        fraccion_perdidas_red=0.15, fraccion_efluente_cloacal=0.8
    )
    con_perdidas = resolver(cuenca, RED)

    provision = sin_perdidas.valores["agua_potable"]
    fugado = 0.15 * provision
    assert con_perdidas.flujos_internos["perdidas_red"] == pytest.approx(fugado)
    assert con_perdidas.valores["descarga_planta"] == pytest.approx(0.8 * provision)
    assert con_perdidas.valores["escurrimiento_subsuperficial"] == pytest.approx(
        sin_perdidas.valores["escurrimiento_subsuperficial"] + fugado
    )
    assert con_perdidas.reparto.fraccion_uso_exterior == pytest.approx(0.05)


def test_el_uso_exterior_queda_dentro_de_la_et(cuenca):
    # Si baja el efluente, lo que deja de ir a la planta pasa a ser uso exterior y sale por la ET
    base = resolver(cuenca, RED)
    cuenca.estados["post"].reparto = Reparto(fraccion_efluente_cloacal=0.7)
    menos_efluente = resolver(cuenca, RED)
    corrido = 0.162 * base.valores["agua_potable"]
    assert menos_efluente.valores["evapotranspiracion"] == pytest.approx(
        base.valores["evapotranspiracion"] + corrido
    )


def test_el_reparto_no_puede_pasar_de_toda_la_provision():
    with pytest.raises(ErrorDeCaso, match="no pueden pasar"):
        Reparto(fraccion_perdidas_red=0.3, fraccion_efluente_cloacal=0.8)


def test_el_aporte_de_aguas_arriba_es_solo_entrada(cuenca):
    sin_aporte = replace(cuenca, componentes={
        k: v for k, v in cuenca.componentes.items() if k != "aporte_aguas_arriba"
    })
    for nombre in (PRE, RED, POZOS):
        con, sin = resolver(cuenca, nombre), resolver(sin_aporte, nombre)
        assert con.valores["escurrimiento_subsuperficial"] == sin.valores[
            "escurrimiento_subsuperficial"
        ]
        # no se asigna a ninguna salida: termina en el cierre
        assert con.valores["evapotranspiracion"] == pytest.approx(
            sin.valores["evapotranspiracion"] + 108
        )


def test_toml_y_csv_de_la_misma_cuenca_dan_el_mismo_balance(cuenca):
    desde_toml = leer_toml(escribir_toml(cuenca))
    desde_csv = leer_csv(escribir_csv(cuenca))
    for original, a, b in zip(
        resolver_todos(cuenca), resolver_todos(desde_toml), resolver_todos(desde_csv)
    ):
        assert original.valores == a.valores == b.valores
        assert original.caso == a.caso == b.caso
    assert desde_csv.nombre == cuenca.nombre
    assert desde_csv.area_km2 == cuenca.area_km2
    assert desde_csv.estados["post"].reparto == cuenca.estados["post"].reparto


def test_un_nombre_de_caso_con_comas_sobrevive_al_csv(cuenca):
    cuenca.casos[0] = Caso('Pre, "natural"', "pre")
    assert leer_csv(escribir_csv(cuenca)).casos[0].nombre == 'Pre, "natural"'
    assert leer_toml(escribir_toml(cuenca)).casos[0].nombre == 'Pre, "natural"'


def test_la_componente_de_cierre_no_se_carga_en_los_estados():
    with pytest.raises(ErrorDeCaso, match="no se carga en el estado pre"):
        Cuenca(
            nombre="Cierre cargado",
            area_km2=1.0,
            cierre="evapotranspiracion",
            estados={"pre": EstadoUrbanizacion("pre", {"evapotranspiracion": mm(400)})},
        )


def test_un_caso_pre_no_tiene_saneamiento():
    with pytest.raises(ErrorDeCaso, match="no puede tener saneamiento"):
        Caso("Pre con red", "pre", "red")


def test_cada_dato_se_carga_en_su_nivel():
    with pytest.raises(ErrorDeCaso, match="no se carga en la cuenca"):
        Cuenca(nombre="X", area_km2=1.0, componentes={"escurrimiento_superficial": mm(10)})
    with pytest.raises(ErrorDeCaso, match="no se carga en el estado post"):
        EstadoUrbanizacion("post", {"precipitacion": mm(10)})


def test_avisa_si_la_componente_de_cierre_da_negativa():
    cuenca = Cuenca(
        nombre="Cierre imposible",
        area_km2=1.0,
        componentes={"precipitacion": mm(700)},
        cierre="evapotranspiracion",
        estados={"pre": EstadoUrbanizacion("pre", {"escurrimiento_superficial": mm(900)})},
        casos=[Caso("Pre", "pre")],
    )
    resultado = resolver(cuenca, "Pre")
    assert resultado.valores["evapotranspiracion"] == pytest.approx(-200)
    assert any("negativa" in aviso for aviso in advertencias(resultado))


def test_una_componente_vieja_avisa_como_se_carga_ahora():
    with pytest.raises(ErrorDeCaso, match="escurrimiento_superficial"):
        EstadoUrbanizacion("pre", {"escurrimiento_directo": mm(100)})
    with pytest.raises(ErrorDeCaso, match="fraccion_efluente_cloacal"):
        EstadoUrbanizacion("post", {"vertido_pozos": mm(100)})
    with pytest.raises(ErrorDeCaso, match="fraccion_efluente_cloacal"):
        EstadoUrbanizacion("post", {"descarga_planta": mm(100)})


def test_un_archivo_de_caso_suelto_explica_el_formato_nuevo():
    viejo = 'nombre = "Viejo"\nsaneamiento = "red"\narea_km2 = 12.5\n'
    with pytest.raises(ErrorDeCaso, match="formato viejo"):
        leer_toml(viejo)
    with pytest.raises(ErrorDeCaso, match="formato viejo"):
        leer_csv("componente,campo,valor\ncaso,nombre,Viejo\n")


# --- Esquema tipo apunte: que no se corte con ningún juego de valores ---

_BASE = resolver_todos(leer(EJEMPLO))


def _con(resultado, **valores):
    return replace(resultado, valores={**resultado.valores, **valores})


ESQUEMAS = {
    **{r.caso.nombre: r for r in _BASE},
    # pocas ramas arriba y muchas abajo: pasaba en pre-urbanización y colgaban afuera
    "una rama arriba": _con(_BASE[1], agua_potable=0, aporte_aguas_arriba=0, evapotranspiracion=0),
    # una sola rama por lado: el tronco lo define el rótulo del almacenamiento
    "una rama por lado": _con(
        _BASE[0], aporte_aguas_arriba=0, evapotranspiracion=0,
        escurrimiento_subsuperficial=0, escurrimiento_subterraneo=0,
    ),
    "todo en cero": replace(_BASE[0], valores=dict.fromkeys(_BASE[0].valores, 0.0)),
    "almacenamiento grande": _con(_BASE[0], almacenamiento_humedad=-12345),
    "pozos grandes": _con(_BASE[2], vertido_pozos=98765),
}


@pytest.fixture(params=list(ESQUEMAS), ids=list(ESQUEMAS))
def figura(request):
    from balance.graficos import esquema

    return esquema(ESQUEMAS[request.param])


def test_toda_rama_del_esquema_toca_el_tronco(figura):
    ax = figura.axes[0]
    tronco, *ramas = ax.patches
    izq, der = tronco.get_xy()[:, 0].min(), tronco.get_xy()[:, 0].max()
    for rama in ramas:
        xs = rama.get_xy()[:, 0]
        assert izq - 1e-9 <= xs.min() and xs.max() <= der + 1e-9


def test_nada_del_esquema_queda_afuera_de_la_figura(figura):
    ax = figura.axes[0]
    renderer = figura.canvas.get_renderer()
    marco = ax.get_window_extent(renderer)
    for artista in (*ax.patches, *ax.lines, *ax.texts):
        caja = artista.get_window_extent(renderer)
        assert marco.x0 <= caja.x0 and caja.x1 <= marco.x1, artista
        assert marco.y0 <= caja.y0 and caja.y1 <= marco.y1, artista
    titulo = ax.title.get_window_extent(renderer)
    assert 0 <= titulo.x0 and titulo.x1 <= figura.bbox.x1
    assert titulo.y1 <= figura.bbox.y1
