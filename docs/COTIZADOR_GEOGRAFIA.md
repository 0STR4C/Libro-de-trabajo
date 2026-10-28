# Cotizador: direcciones, territorio y moneda

## Cobertura efectiva

| Recorrido | Identificación de puntos | Precio automático en UYU |
| --- | --- | --- |
| Interior de Uruguay, incluida salida de grúa opcional | Coordenadas, enlace de Google Maps o dirección elegida de las sugerencias | Sí, si OSRM devuelve una geometría completa dentro de Uruguay. Se aplican las tarifas vigentes sin cambios. |
| Interior de Argentina o Brasil | Coordenadas y sugerencias del geocodificador | No. Falta una tarifa comercial para esos países. |
| Transfronterizo, incluso si los extremos están en Uruguay pero la ruta sale del país | Puntos y recorrido identificables | No. No se calcula ni guarda un precio. |
| Distancia manual sin ubicaciones identificadas | Kilómetros ingresados por el operador | Conserva el comportamiento anterior. La pantalla advierte que la tarifa vigente corresponde solo a recorridos uruguayos; el sistema no puede inferir el país a partir de kilómetros. Si hay coordenadas conocidas, también las valida. |

La búsqueda de direcciones no habilita por sí sola una tarifa regional. El backend verifica el polígono departamental uruguayo que ya usa la aplicación (`app/static/uruguay-departamentos.geojson`) para cada extremo y cada punto de la ruta; un punto exterior impide cotizar y persistir. Cerca de la frontera, la precisión de ese GeoJSON puede producir rechazos conservadores. No se convierte moneda ni se cambia el criterio de peajes o kilómetros.

## Diagnóstico de la coordenada reportada

Para origen `-34.813803, -55.238921` y destino `-33.979809, -58.382095`, sin salida de la grúa, el parser conserva el orden latitud/longitud. El GeoJSON abarca en conjunto longitudes `-58.4391…-53.1836` y latitudes `-34.9738…-30.0856`: **ambos puntos están dentro de ese rectángulo**, pero el primer punto está dentro de un polígono departamental y el segundo queda fuera. Por ello, la versión anterior rechazaba **el destino antes de llamar a OSRM**, sin crear una cotización. En una consulta diagnóstica al servicio OSRM configurado el 26 de octubre de 2026, `nearest` ajustó el destino a `-33.957245, -58.356012`, **3.475 m** del pin original; el punto ajustado sí cae dentro del polígono. El endpoint `route` devolvió el mismo ajuste. La geocodificación inversa de OSM devolvió solamente la entidad administrativa «Uruguay», sin calle para el pin original. Estos datos no prueban si el agua está bajo jurisdicción uruguaya, pero sí muestran que el pin no representa una vía cercana apta para un cálculo vial confiable. Se conserva el rechazo y se permite verificar y arrastrar el pin a una calle próxima.

Además del polígono, el Cotizador comprueba los puntos ajustados por OSRM. Si el ajuste supera **500 m**, detiene el cálculo e informa qué extremo del tramo no tiene una vía suficientemente cercana. Este límite es una salvaguarda técnica contra kilómetros inventados por un ajuste lejano, no una tarifa. En zonas rurales puede requerir que el operador coloque el pin sobre la vía de acceso o use la modalidad manual con criterio humano. La geometría completa y sus puntos intermedios siguen protegidos contra recorridos que salen de Uruguay.

## Geocodificación y rutas para Sistemas

La API interna `/api/quotes/geocode?q=...&country=UY` requiere permiso `quotes.create` y habla con una instancia compatible con [Photon](https://github.com/komoot/photon/blob/master/docs/api-v1.md). Envía el texto de búsqueda, limitado a 120 caracteres, y filtra por el país elegido: `UY`, `AR` o `BR`. Devuelve hasta 12 nombres legibles y coordenadas. El navegador espera 450 ms desde la última edición, cancela la consulta anterior y exige que el operador elija una opción; no geocodifica cada pulsación. La petición al proveedor tiene un límite de cinco segundos. No hay credenciales en el frontend ni en el repositorio. `/api/quotes/resolve-location` interpreta coordenadas o enlaces y permite confirmar el pin sobre el mapa antes de cotizar.

La búsqueda local fallaba porque enviaba `lang=es`; la instancia pública respondió HTTP 400 con idiomas habilitados `default`, `de`, `en` y `fr`. Ahora se omite ese parámetro y Photon devuelve los nombres locales. Desde el contenedor se verificó una respuesta real para «18 de Julio 1234 Montevideo»; «18 de Julio y Ejido Montevideo» devolvió varias sugerencias, por lo que el operador debe elegir una. Una intersección puede devolver números o lugares cercanos: hay que confirmar el pin antes de informar un precio.

- En desarrollo, si `GEOCODER_URL` está vacío, se usa `https://photon.komoot.io` para pruebas manuales de bajo volumen. [Photon aclara que su servidor público es una demostración sin garantía de disponibilidad y puede limitar o bloquear usos extensos](https://github.com/komoot/photon/blob/master/README.md#demo-server).
- En producción (`APP_ENV=production`), Sistemas debe configurar `GEOCODER_URL` con la URL base de una instancia Photon propia o un servicio contratado compatible. Sin esa configuración, la búsqueda informa que no está disponible; las coordenadas y enlaces siguen funcionando. Una instancia propia exige planificar datos, memoria, almacenamiento, actualizaciones y monitoreo según la [guía de Photon](https://github.com/komoot/photon/blob/master/docs/usage.md).
- No se usa el servidor público de Nominatim para sugerencias: su [política prohíbe el autocompletado cliente y limita las solicitudes](https://operations.osmfoundation.org/policies/nominatim/).
- `OSRM_BASE_URL` permite reemplazar `https://router.project-osrm.org`. El servidor público de OSRM es [un servicio de demostración sin garantías de disponibilidad ni calidad](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server). Para operación sostenida, Sistemas debe configurar un motor de rutas propio o contratado con cobertura uruguaya y verificar sus datos viales; el Cotizador no ha certificado rutas regionales.

Las latencias y disponibilidad reales dependen de la instancia y la red de Sistemas. Las pruebas automatizadas simulan respuestas de Photon y OSRM; no realizan consultas a esos servicios.
