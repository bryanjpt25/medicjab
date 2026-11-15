# Astro Health Monitor — proyecto modular

Prototipo web de monitoreo fisiológico para misiones espaciales. El proyecto conserva la interfaz y los escenarios simulados, pero separa la estructura, los estilos y la lógica en archivos independientes.

## Estructura

```text
astro-health-modular/
├── index.html                 # Estructura de la página
├── css/
│   └── styles.css             # Diseño, colores y distribución
├── js/
│   ├── main.js                # Punto de entrada de la aplicación
│   ├── state.js               # Estado compartido
│   ├── scenarios.js           # Datos de los escenarios de riesgo
│   ├── ui.js                  # Botones, astronauta, tarjetas y cuerpo
│   └── ecg.js                 # ECG animado y variación de muestras
├── assets/
│   └── anatomia_azul.png      # Ilustración anatómica azul
└── README.md
```

## Cómo ejecutarlo en Visual Studio Code

1. Descomprime la carpeta del proyecto.
2. Abre **la carpeta completa** `astro-health-modular` en VS Code (no abras solamente `index.html`).
3. Instala la extensión **Live Server** si todavía no la tienes.
4. Haz clic derecho en `index.html` y elige **Open with Live Server**.
5. La aplicación se abrirá en el navegador mediante `http://localhost:...`.

> Se usa JavaScript con módulos (`type="module"`). Por eso conviene abrirlo con Live Server y no mediante doble clic (`file://`).

## Reparto recomendado del trabajo

| Integrante | Archivos | Responsabilidad |
|---|---|---|
| 1. Interfaz | `index.html`, `css/styles.css` | Estructura, paneles y diseño adaptable |
| 2. Escenarios | `js/scenarios.js` | Valores y descripciones de cada peligro |
| 3. Interacción | `js/ui.js`, `js/state.js` | Botones, marcadores anatómicos y actualización de tarjetas |
| 4. Señales | `js/ecg.js` | ECG, ruido y actualización de muestras |
| Integración | `js/main.js`, `README.md` | Conectar módulos y comprobar el funcionamiento |

## Reglas para trabajar en equipo

- Antes de editar, acuerden quién será responsable de cada archivo.
- Eviten que dos personas modifiquen el mismo archivo al mismo tiempo.
- Cada integrante puede crear una rama Git para su tarea y luego abrir un Pull Request.
- No cambien los nombres de los IDs del HTML sin coordinarlo con `ui.js` y `ecg.js`, porque JavaScript los utiliza para encontrar los elementos.
- Mantengan `assets/anatomia_azul.png` dentro de la carpeta `assets`.

## Importante

Los valores fisiológicos, la señal ECG y los escenarios de esta versión son simulados. El interruptor “IA a bordo” no ejecuta todavía un modelo real de IA. No utilizar como sistema de diagnóstico médico.
