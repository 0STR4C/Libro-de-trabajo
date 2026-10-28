# Validación técnica local

`run.ps1` ejecuta Python, Node y Vite dentro de Docker, sin instalar paquetes en
el host ni usar la base operativa. Antes de compilar Vite reconstruye la imagen
frontend predeterminada desde el `package-lock.json` vigente; Docker reutiliza
la caché y solo descarga dependencias cuando cambian. Una imagen frontend
personalizada se usa tal como se entregó y el resultado indica que no se
reconstruyó. La suite general usa la imagen de pruebas Pytest existente
para casos de dominio y la suite PostgreSQL usa un proyecto Compose único por
corrida. La compilación Vite ocurre en el contenedor y descarta sus salidas.

```powershell
& .\tools\test_all\run.ps1
```

Las imágenes predeterminadas son `librodetrabajo-app:latest`,
`librodetrabajo-delays-pytest:local`, `librodetrabajo-frontend-check:latest` y
`node:22-alpine`. Para otra versión, indicar la imagen de aplicación y la imagen
Pytest derivada de ella:

```powershell
& .\tools\test_all\run.ps1 -ImageName app-candidata:local -PytestImageName pruebas-candidatas:local
```

El resultado identifica cada etapa aprobada, fallida, omitida o bloqueada.
`-SkipUiSmoke` se mantiene por compatibilidad y registra la omisión. Las pruebas
de navegador históricas usan `legacy_archive` y no validan la interfaz React.
Las ocho suites de layout antiguas se conservan como registro histórico y están
marcadas como omitidas; Vite solo valida compilación. La interacción visual del
React vigente se prueba por separado con `tools/browser_interaction/`.
`-Coverage` informa que el medidor opcional no está disponible en la imagen
actual. Ninguna de estas limitaciones se anuncia como validación visual completa.

Las pruebas PostgreSQL crean y eliminan únicamente los recursos del proyecto
efímero de esa ejecución. Para un caso específico, usar
`tools/postgres_test_db/run.ps1` con `-TestCommand`. No se comparten el puerto,
el volumen ni el contenedor de la base manual `librodetrabajo-tests`.
