# Peajes locales del cotizador

## Alcance

El cotizador detecta los peajes registrados localmente cuando calcula una ruta
automática. Evalúa por separado el recorrido de salida de la grúa al origen y
el traslado del origen al destino. Una misma estación se cobra nuevamente si
se atraviesa en ambos tramos.

Cada cotización guarda la cantidad, las estaciones detectadas, el tramo y el
importe aplicado. Esos datos se muestran en el resultado, historial y CSV.
Las cotizaciones manuales no agregan peajes porque no cuentan con un trazado
geográfico verificable.

## Carga inicial

1. Ingresar como Administrador a **Configuración → Catálogos**.
2. Elegir **Agregar peaje**.
3. Pegar las coordenadas exactas de la estación en un único campo, por ejemplo
   `-34.78555120875285, -55.88979771379574`, o pegar el enlace completo de
   Google Maps. El formulario completa latitud y longitud automáticamente.
4. Dejar la tarifa propia vacía para usar la tarifa general de la cobertura, o
   informarla únicamente si esa estación tiene un precio diferente.
5. Verificar la tarifa general en **Configuración → Tarifas cotizador**.

La tolerancia de coincidencia es de 300 metros. Por seguridad, el catálogo
comienza vacío: no se cargaron coordenadas aproximadas ni se usaron servicios
de Google Cloud. Antes de usarlo en operación, validar una cotización de prueba
que atraviese un peaje conocido y confirmar el detalle mostrado.

## Archivos relevantes

- `app/tolls.py`: detección geométrica local y reutilizable.
- `tests/test_tolls.py`: pruebas unitarias de los pasajes por tramo.
- `app/postgres_server.py`: catálogo, cálculo y persistencia para Docker/PostgreSQL.
- `app/local_server.py`: comportamiento equivalente en modo local.

## Verificación

Ejecutar desde la raíz del proyecto:

```powershell
& 'C:\Users\OSTRA\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests -q
```

No modifica ni reemplaza `centro_operativo.db`.
