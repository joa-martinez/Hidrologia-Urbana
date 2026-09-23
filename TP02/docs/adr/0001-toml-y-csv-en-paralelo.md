# Los casos se cargan y guardan en TOML y en CSV/Excel

Los casos de balance podrían definirse únicamente en TOML, que Python lee sin dependencias
(`tomllib`) y versiona bien. Aun así se soportan también CSV/Excel porque los compañeros de
cátedra que van a usar la app trabajan en planillas y no editarían un TOML a mano. El CSV usa
formato largo (`componente,campo,valor`) en vez de una columna por parámetro, para que agregar
un método de cálculo nuevo no rompa los archivos existentes ni llene la planilla de celdas vacías.

## Consecuencias

Hay dos lectores y dos escritores que mantener en paralelo, y un test que verifica que el mismo
caso expresado en los dos formatos produzca resultados idénticos.
