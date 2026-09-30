# CSV a JSON para Fusion

Convierte un CSV (por ejemplo, un Excel guardado como CSV) en JSON donde **cada fila es un objeto con el nombre de cada columna**, listo para leerlo en un escenario de Adobe Workfront Fusion. Sale completo o partido para que cada parte entre en un webhook.

Todo corre en el navegador: el archivo **no se sube a ningún lado**.

## Cómo usarla

1. Abre `csv-a-json.html` con doble clic (funciona sin internet), o la versión publicada en Netlify.
2. Arrastra el CSV. La herramienta detecta la codificación y el separador, y muestra cuántas filas y columnas encontró.
3. Elige la salida:

   | Modo | Para qué |
   |---|---|
   | **Completo** | Un solo JSON con todas las filas, para subirlo como documento. |
   | **Partido por tamaño** | Partes de hasta 5 MB (el tope de un webhook de Fusion). Por defecto 4,5 MB. |
   | **Partido por filas** | Partes con un número fijo de filas, por ejemplo un lote por ejecución. |

4. **Convertir**. Antes de dejarte descargar, vuelve a leer lo que generó y lo compara contra el CSV fila por fila.

Un Excel (`.xlsx`) hay que guardarlo antes como CSV desde Excel.

## Qué garantiza

La conversión es **fiel**:

- Las llaves son los encabezados **exactos** del archivo; los valores, el texto **exacto** de cada celda.
- No agrega campos, no quita columnas (ni las vacías), no recorta espacios, no convierte números ni fechas: `00123` sigue siendo `"00123"`.
- Lo único que cambia es cómo se guarda el texto: un CSV de Excel en español viene en Windows-1252 y el JSON sale en UTF-8, que es lo que lee Fusion. Los caracteres son los mismos.

Ejemplo, con `ejemplo.csv`:

```json
{"SKU": "00124", "DESCRIPCIÓN": "Galletas; surtidas", "PRECIO": "45", "INICIO": "2026-10-01", "FIN": "2026-10-15", "NOTAS": "Texto con \"comillas\""}
```

Si algo impediría una conversión fiel, **no convierte** y dice por qué:

- dos columnas con el mismo nombre (en JSON una pisaría a la otra);
- filas con más o menos columnas que el encabezado.

Además avisa, sin cambiar nada, cuando hay filas repetidas, líneas vacías o encabezados con tildes.

## En Fusion

Cada archivo es un arreglo JSON de objetos. Se lee con **JSON › Parse JSON** usando una estructura de datos (se genera pegando una fila de ejemplo) y se recorre con un **Iterator**. Así el panel de mapeo muestra cada campo por su nombre, no por su posición.

## Tecnología

- **HTML + CSS + JavaScript**, sin librerías ni dependencias. Un solo archivo.
- La página no hace ninguna petición de red.
- Python solo se usa para armar la carpeta de Netlify y para las pruebas.

## Publicar en Netlify

**Opción A, arrastrar la carpeta:**

```bash
python3 build_netlify.py
```

Luego arrastra la carpeta `dist/` a [app.netlify.com/drop](https://app.netlify.com/drop).

**Opción B, conectar el repositorio:** en Netlify, *Add new site › Import an existing project* y elige este repo. `netlify.toml` ya le dice qué comando correr y qué carpeta publicar.

`build_netlify.py` separa el HTML en `index.html`, `estilo.css`, `core.js` y `ui.js` para poder mandar una política de seguridad estricta:

- solo código y estilos del mismo sitio (`script-src 'self'`, `style-src 'self'`);
- la página no puede conectarse a ningún servidor (`connect-src 'none'`), así que aunque quisiera no podría mandar el archivo a ningún lado;
- no se puede embeber en otro sitio y no aparece en buscadores.

Si queda algo que rompa esa política, el script borra la carpeta y avisa.

## Pruebas

```bash
python3 pruebas/paridad.py
```

Corre el mismo código de la página (con Node) y el módulo `csv` de Python sobre los mismos datos y exige el mismo resultado: comillas, `""` escapadas, separadores y saltos de línea dentro de comillas, CRLF, BOM, Windows-1252, líneas vacías y 5.000 textos al azar. Después prueba los tres modos de salida de punta a punta sobre `ejemplo.csv`. Requiere `python3` y `node`.

## Archivos

| Archivo | Qué es |
|---|---|
| `csv-a-json.html` | La herramienta. Es la fuente: todo lo demás sale de aquí. |
| `build_netlify.py` | Arma `dist/` para Netlify. |
| `netlify.toml` | Configuración para publicar desde el repositorio. |
| `ejemplo.csv` | Datos inventados con los casos difíciles, para probar. |
| `pruebas/paridad.py` | Prueba contra el módulo `csv` de Python. |

**No subas archivos reales a este repositorio.** El `.gitignore` bloquea `*.csv`, `*.xlsx` y `*.json` (salvo `ejemplo.csv`) para evitarlo por accidente.
