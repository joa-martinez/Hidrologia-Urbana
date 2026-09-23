# Visualizador del balance hidrológico anual

App para plantear el Balance Hidrológico Anual de una cuenca urbana (Cap. 2 de
*Hidrología e Hidráulica en Territorios Urbanizados*) y comparar casos: antes de
urbanizar, urbanizada con red cloacal, y urbanizada con pozos absorbentes.

## Cómo usarla

Online, sin instalar nada: **https://balance-hidrologico.streamlit.app/**

Si nadie la usó en los últimos días, la app está dormida: tocar el botón para
despertarla y esperar alrededor de un minuto.

## Cómo correrla en tu compu

Doble clic en `correr.sh` (Linux/macOS) o en `correr.bat` (Windows). La primera vez
crean el entorno e instalan las dependencias solas; después abren la app en
http://localhost:8501.

A mano:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

## Cómo se cargan los datos

Un archivo por **cuenca**, con toda la comparación adentro. Se usa TOML
(`cuencas/ejemplo_apunte.toml` sirve de plantilla) o una planilla CSV/Excel en formato largo.
Los datos van en tres niveles, para que los casos se comparen sobre la misma cuenca:

- **Cuenca**: lo que no cambia entre casos. Área, precipitación, aporte desde aguas
  arriba, provisión de agua potable (dotación y población) y la **componente de
  cierre**, que es la misma en todos los casos.
- **Estado de urbanización** (`pre` y `post`): escurrimiento superficial, parte base del
  subsuperficial, subterráneo, almacenamiento en humedad del suelo y, si no es el cierre,
  la ET. El estado `post` suma el **reparto de la provisión**: `fraccion_perdidas_red` y
  `fraccion_efluente_cloacal`. Lo que queda es uso exterior (riego, limpieza), que
  termina dentro de la ET.
- **Caso**: solo elige su estado y su saneamiento (`red`, `pozos` o `ninguno`).

```csv
ambito,elemento,campo,valor
cuenca,,nombre,Cuenca del apunte
cuenca,,area_km2,12.5
cuenca,,cierre,evapotranspiracion
cuenca,precipitacion,valor_mm,743
cuenca,agua_potable,metodo,dotacion
cuenca,agua_potable,dotacion_l_hab_dia,300
cuenca,agua_potable,poblacion,60388
pre,escurrimiento_superficial,metodo,coeficiente
pre,escurrimiento_superficial,coeficiente,0.1
post,,fraccion_perdidas_red,0.15
post,,fraccion_efluente_cloacal,0.8
caso,Pre-urbanización,estado,pre
caso,Post-urbanización con red cloacal,estado,post
caso,Post-urbanización con red cloacal,saneamiento,red
```

La columna `ambito` es `cuenca`, `pre`, `post` o `caso`. En `elemento` va la componente,
vacía si el dato es suelto, como el área o las fracciones. En las filas `caso`, `elemento`
es el nombre del caso.

Cada componente se define con un **valor directo** (`valor_mm`, `valor_hm3`,
`valor_m3` o `valor_l_s`) o con un **método de cálculo**. Una componente ausente vale 0.
Todo se convierte a mm/año. Con `cierre = "ninguno"` no se despeja nada y se muestra
el residuo.

Métodos disponibles: `dotacion`, `fraccion_precipitacion`, `coeficiente`,
`coeficiente_ponderado`.

El balance sigue la ecuación (2.8) del Cap. 2, `P + S = E + ΔF + ΔG`. La
evapotranspiración va toda junta (incluye la evaporación del agua potable usada) y
suele ser la componente de cierre, por ser la más difícil de estimar. El reparto de la
provisión funciona así:

- las **pérdidas de red** se infiltran y salen por el escurrimiento subsuperficial;
- el **efluente cloacal** sale por la **descarga de planta** con red cloacal, o se
  infiltra y sale por el **escurrimiento subsuperficial** con pozos absorbentes (por eso
  los gráficos aclaran que ese escurrimiento viene en parte de los pozos);
- el **uso exterior**, lo que queda, no se asigna y termina dentro de la ET.

El aporte desde aguas arriba es solo una entrada: no se suma a ningún escurrimiento.

Desde la app se edita la cuenca en pantalla y se descarga en TOML o CSV.

## Estructura

- `balance/modelo.py` — componentes, cuenca, estados, casos y resolución del balance
- `balance/carga.py` — lectura y escritura en TOML y CSV/Excel
- `balance/graficos.py` — barras y Sankey (plotly), esquema tipo apunte (matplotlib)
- `balance/validacion.py` — advertencias sobre un caso resuelto
- `app.py` — interfaz Streamlit
- `cuencas/` — la cuenca de ejemplo con sus tres casos, con los valores del esquema del apunte
- `CONTEXT.md` — glosario del dominio; `docs/adr/` — decisiones de diseño

```bash
.venv/bin/python -m pytest tests -q
```
