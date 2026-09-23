# Balance hidrológico urbano

Balance hídrico anual de una cuenca urbana, comparado entre distintos escenarios de urbanización y saneamiento.

## Language

**Balance hidrológico anual**:
Contabilidad de las entradas y salidas de agua de la cuenca durante un año, que debe cerrar (entradas = salidas + variación de almacenamiento).

**Cuenca**:
El territorio que se estudia, con los datos que no cambian de un **Caso** a otro: área, **Precipitación**, **Aporte desde aguas arriba**, los parámetros de la **Provisión de agua potable** (dotación y población) y la **Componente de cierre**. Todos los **Casos** comparten la misma **Cuenca**, así la comparación es entre estados de urbanización y no entre cuencas distintas. El **Caso** Pre-urbanización no usa la provisión.

**Caso**:
Un escenario de la **Cuenca** para el que se plantea un balance. Hay tres: **Pre-urbanización**, **Post-urbanización con red** y **Post-urbanización con pozos absorbentes**. Se define por su **Estado de urbanización** y su **Saneamiento**. No puede modificar los datos de la **Cuenca** ni los de su **Estado de urbanización**. Lo único propio del **Caso** es el **Saneamiento**, que decide adónde va el **Efluente cloacal**.
_Avoid_: escenario, alternativa

**Estado de urbanización**:
Qué tan urbanizada está la **Cuenca**: **Pre** o **Post**. Reúne lo que depende de la urbanización y no del **Saneamiento**: **Escurrimiento superficial**, la parte base del **Escurrimiento subsuperficial**, **Escurrimiento subterráneo**, **Almacenamiento en humedad del suelo**, **Reparto de la provisión** y la **Evapotranspiración (ET)** cuando no es la **Componente de cierre**. El **Caso** Pre-urbanización es el único con estado Pre. Los dos **Casos** urbanizados comparten un mismo estado Post.

**Componente**:
Cada flujo o variación de almacenamiento que interviene en el **Balance hidrológico anual**. Su valor puede cargarse directamente o calcularse a partir de parámetros. Sigue la ecuación (2.8) del Cap. 2: `P + S = E + ΔF + ΔG`. Listado vigente:

- Entradas:
  - **Precipitación**
  - **Provisión de agua potable**
  - **Aporte desde aguas arriba**: flujo que ingresa a la cuenca desde aguas arriba (en el apunte, filtración subsuperficial). Su origen y su camino dentro de la cuenca no se conocen, así que solo se contabiliza como entrada: no se asigna a ninguna salida en particular.
- Salidas:
  - **Evapotranspiración (ET)**: una sola, incluye la evaporación del sistema de agua potable. Es la más difícil de estimar, así que suele ser la **Componente de cierre**.
  - **Escurrimiento superficial**
  - **Escurrimiento subsuperficial**: una parte base, que es dato del **Estado de urbanización**, más los flujos internos que se infiltran en la cuenca (**Pérdidas de red de agua potable** y **Vertido a pozos absorbentes**).
  - **Escurrimiento subterráneo**
  - **Descarga de planta cloacal**: solo con **Red cloacal**.
- Variación de almacenamiento:
  - **Almacenamiento en humedad del suelo**

**Método de cálculo**:
Forma de obtener el valor de una **Componente** a partir de parámetros de la cuenca (dotación y población, coeficiente de escurrimiento, fracción de la provisión, etc.), en lugar de cargarla como valor directo. Una **Componente** define un valor directo o un **Método de cálculo**, nunca ambos.

**Componente de cierre**:
**Componente** que se designa como incógnita y se despeja del balance. Se elige una vez en la **Cuenca** y es la misma en todos los **Casos**, para que la incógnita absorba el error en el mismo lugar en todos. Es opcional: si no hay, todos los **Casos** muestran su **Residuo**.

**Residuo**:
Diferencia entre entradas y (salidas + variación de almacenamiento) cuando ninguna **Componente de cierre** está designada. Se expresa en valor absoluto y en % de las entradas.
_Avoid_: error de cierre, desbalance

**Saneamiento**:
Cómo trata el **Caso** los efluentes cloacales: **Red cloacal**, **Pozo absorbente** o ninguno.

**Red cloacal**:
Sistema que colecta los efluentes cloacales (agua potable usada) y los lleva a una planta de tratamiento, que descarga al cuerpo receptor.
_Avoid_: red de desagües (ambiguo con pluvial)

**Pérdidas de red de agua potable**:
Fracción de la **Provisión de agua potable** que se fuga de la red, se infiltra y sale por el **Escurrimiento subsuperficial**. Es uno de los destinos del **Reparto de la provisión**. Flujo interno, no es **Componente**: el agua no sale de la cuenca por ahí.

**Pozo absorbente**:
Alternativa a la **Red cloacal**: los efluentes cloacales se infiltran en el suelo en cada lote, alimentando el flujo subsuperficial.

**Vertido a pozos absorbentes**:
Lo que los **Pozos absorbentes** infiltran en el suelo. Flujo interno, no es **Componente**: sale de la cuenca por el **Escurrimiento subsuperficial**, que por eso es mayor con pozos que con **Red cloacal**. Cumple el papel que tiene la **Descarga de planta cloacal** en el caso con red, pero sin sacar el agua de la cuenca directamente.

**Reparto de la provisión**:
División de la **Provisión de agua potable** en tres destinos: **Pérdidas de red de agua potable**, **Efluente cloacal** y **Uso exterior**. Se cargan las fracciones de los dos primeros (su suma no puede pasar de 1) y el **Uso exterior** es lo que queda. Es dato del **Estado de urbanización** Post, así que es el mismo con **Red cloacal** y con **Pozo absorbente**.

**Efluente cloacal**:
Fracción de la **Provisión de agua potable** que se consume y vuelve como líquido cloacal. El **Saneamiento** decide adónde va: con **Red cloacal**, a la **Descarga de planta cloacal**; con **Pozo absorbente**, al **Vertido a pozos absorbentes**.

**Uso exterior**:
Fracción de la **Provisión de agua potable** que se usa fuera de las viviendas (riego, limpieza, recreación): lo que queda después de las pérdidas y el efluente. No va a la cloaca. En realidad una parte se infiltra y otra se evapotranspira, pero no se reparte: queda implícito dentro de la **Evapotranspiración (ET)** cuando ésta es la **Componente de cierre**. Es una simplificación a propósito.
