# Recursos históricos de pruebas

`wfm.js` y `wfm.css` conservan la implementación anterior requerida por
`tools/wfm_offline_build/ui_smoke.cjs`. No se cargan desde `index.html`, no se
sirven como recursos públicos y se excluyen del contexto Docker. El módulo
vigente es `frontend/wfm.jsx`.

La prueba histórica no acredita la interfaz React. Conservar estos recursos
para reproducir esa herramienta; no usarlos como base de nuevas pantallas.
Para cambios frontend actuales, seguir `tools/frontend_build/README.md`.
