"""La app tiene que mostrar exactamente lo que calcula el núcleo.

Cubre el caso en que el editor reconstruye la cuenca con otros parámetros que los
del archivo (pasó con los dos juegos de parámetros del coeficiente de escurrimiento).
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from balance.carga import leer
from balance.modelo import resolver_todos

RAIZ = Path(__file__).resolve().parent.parent
ESPERADOS = resolver_todos(leer(RAIZ / "cuencas" / "ejemplo_apunte.toml"))


@pytest.mark.parametrize("esperado", ESPERADOS, ids=lambda r: r.caso.nombre)
def test_la_app_muestra_lo_mismo_que_el_nucleo(esperado):
    app = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    app.sidebar.selectbox[0].set_value(esperado.caso.nombre).run()

    assert not app.exception
    assert not app.error
    metricas = {m.label: m.value for m in app.metric}
    assert metricas["Entradas"] == f"{esperado.total_entradas:.0f} mm/año"
    assert metricas["Salidas"] == f"{esperado.total_salidas:.0f} mm/año"
    assert metricas["Cierre"] == f"{esperado.valores[esperado.clave_cierre]:.0f} mm/año"
