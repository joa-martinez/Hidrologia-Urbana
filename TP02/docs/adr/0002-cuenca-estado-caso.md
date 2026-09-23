# Los datos se organizan en Cuenca, Estado de urbanización y Caso

Un archivo describe una cuenca entera, no un caso suelto. La app sirve para comparar la
misma cuenca en distintos estados de urbanización y saneamiento. Antes, cada caso repetía
el área, la precipitación, el aporte de aguas arriba y la provisión, y nada impedía que
esos datos difirieran sin que nadie lo notara. Ahora hay tres niveles:

- la **Cuenca** tiene lo que no cambia entre casos, incluida la componente de cierre, para
  que la incógnita absorba el error en el mismo lugar en todos los casos;
- el **Estado de urbanización** (pre o post) tiene lo que depende de cuánto se urbanizó:
  escurrimientos, almacenamiento y el reparto de la provisión;
- el **Caso** solo elige su estado y su saneamiento.

Un caso no puede pisar los datos de los niveles de arriba. Descartamos dos alternativas:
casos autocontenidos con una validación que avise las diferencias (se sigue cargando lo
mismo tres veces), y casos que heredan de otro caso (arma una jerarquía que no existe en
el dominio: el caso con pozos no deriva del caso con red).

El **Vertido a pozos absorbentes** dejó de ser una salida. Es un flujo interno que se
infiltra y sale por el escurrimiento subsuperficial, como las pérdidas de red. Así, el
caso con red y el caso con pozos reparten el mismo efluente cloacal, y la diferencia
entre los dos es por dónde sale: la planta o el subsuelo.

## Consecuencias

- Los archivos de caso suelto del formato anterior ya no se leen. El lector los reconoce
  y explica el formato nuevo.
- No se puede armar un caso "raro" (otra área, otra lluvia) sin crear otra cuenca.
- Con pozos, el escurrimiento subsuperficial crece. Los gráficos lo aclaran, porque si no
  parece que la lluvia se infiltra más.
- El uso exterior de la provisión (riego, limpieza) no se reparte entre infiltración y
  ET: queda implícito en la ET cuando ésta es el cierre. Es una simplificación a
  propósito, para no sumar parámetros.
