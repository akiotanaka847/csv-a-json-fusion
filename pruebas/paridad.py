#!/usr/bin/env python3
"""Prueba de paridad: el parser del navegador contra el modulo csv de Python.

La herramienta promete una conversion FIEL. Esta prueba lo comprueba corriendo el
nucleo real (el <script id="core"> de csv-a-json.html, con Node) y el modulo csv
de Python sobre los mismos bytes, y exigiendo el mismo resultado fila por fila:

  1. casos fijos: comillas, "" escapadas, separador y saltos de linea dentro de
     comillas, CRLF, CR solo, BOM, Windows-1252, lineas vacias, ultima linea sin
     salto, y ejemplo.csv;
  2. miles de textos al azar armados con los caracteres que rompen un CSV
     (; , " \\r \\n espacio y tildes), con semilla fija para que se repitan;
  3. el camino completo sobre ejemplo.csv: objetos -> partes -> JSON -> verificar.

Requiere python3 y node. No usa archivos de nadie: todo sale de aqui o de
ejemplo.csv, que es inventado.

Uso:
    python3 pruebas/paridad.py
    python3 pruebas/paridad.py --casos 20000 --semilla 7
"""

import argparse
import base64
import csv
import io
import json
import pathlib
import random
import re
import subprocess
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "csv-a-json.html"
EJEMPLO = RAIZ / "ejemplo.csv"

# Corre en Node con el mismo Core que usa la pagina. Recibe los casos por stdin.
RUNNER = r"""
const Core = require(process.argv[2]);
const casos = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = casos.map((c) => {
  const bytes = Uint8Array.from(Buffer.from(c.b64, "base64"));
  const d = Core.decodificar(bytes, "auto");
  const sep = c.sep || Core.detectarSeparador(d.texto);
  const p = Core.parsear(d.texto, sep);
  const r = { texto: d.texto, codif: d.codif, sep, filas: p.filas, vacias: p.vacias };
  if (c.completo) {
    const enc = p.filas[0], datos = p.filas.slice(1);
    const objetos = Core.aObjetos(enc, datos);
    r.revision = Core.revisar(enc, datos);
    r.modos = {};
    for (const [modo, valor] of [["completo", 0], ["filas", 2], ["mb", 0.0003]]) {
      const textos = Core.partir(objetos, modo, valor).map((x) => JSON.stringify(x));
      r.modos[modo] = { partes: textos.length, textos, checks: Core.verificar(enc, datos, textos) };
    }
  }
  return r;
});
process.stdout.write(JSON.stringify(out));
"""


def decodificar(b):
    """Lo mismo que Core.decodificar en modo automatico."""
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252")


def filas_python(texto, sep):
    """El modulo csv devuelve [] por cada linea vacia; la herramienta no las
    convierte (las cuenta aparte). Se comparan solo las filas con contenido."""
    return [f for f in csv.reader(io.StringIO(texto, newline=""), delimiter=sep) if f != []]


def casos_fijos():
    t = lambda s, sep=";": {"nombre": repr(s)[:50], "b": s.encode("utf-8"), "sep": sep}
    return [
        t("A;B\n1;2\n"),
        t("A;B\r\n1;2\r\n"),
        t("A;B\r1;2\r"),                            # CR solo (Mac antiguo)
        t("A;B\n1;2"),                              # ultima linea sin salto
        t('A;B\n"x;y";2\n'),                        # separador dentro de comillas
        t('A;B\n"linea 1\nlinea 2";2\n'),           # salto de linea dentro de comillas
        t('A;B\n"linea 1\r\nlinea 2";2\r\n'),
        t('A;B\n"dijo ""hola""";2\n'),              # comillas escapadas
        t('A;B\nab"cd;2\n'),                        # comilla a mitad de campo: es texto
        t('A;B\n"ab"cd;2\n'),                       # texto despues de cerrar comillas
        t("A;B\n\n1;2\n\n\n3;4\n"),                 # lineas vacias
        t("A;B\n  1  ; 2 \n"),                      # espacios: no se recortan
        t("A;B;C\n;;\n"),                           # fila con todas las celdas vacias
        t('A\n""\n'),                               # una sola columna, valor vacio entre comillas
        t('A\n""'),
        t("A,B\n1,2\n", ","),
        t("A\tB\n1\t2\n", "\t"),
        {"nombre": "BOM UTF-8", "b": b"\xef\xbb\xbfA;B\n\xc3\xa1;2\n", "sep": ";"},
        {"nombre": "Windows-1252", "b": "CAMPAÑA;DESCRIPCIÓN\nPiñata;Acción\n".encode("cp1252"), "sep": ";"},
        {"nombre": "ejemplo.csv", "b": EJEMPLO.read_bytes(), "sep": None, "completo": True},
    ]


def casos_azar(n, semilla):
    rnd = random.Random(semilla)
    piezas = ["a", "b", "7", "é", "Ñ", " ", ";", ",", '"', '""', "\n", "\r\n", "\r"]
    casos = []
    for i in range(n):
        s = "".join(rnd.choice(piezas) for _ in range(rnd.randint(0, 40)))
        casos.append({"nombre": f"azar #{i}", "b": s.encode("utf-8"), "sep": ";"})
    return casos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casos", type=int, default=5000, help="textos al azar (default 5000)")
    ap.add_argument("--semilla", type=int, default=1)
    a = ap.parse_args()

    core = re.search(r'<script id="core">(.*?)</script>', FUENTE.read_text(encoding="utf-8"), re.S)
    if not core:
        raise SystemExit("No se encontro <script id=\"core\"> en csv-a-json.html")

    casos = casos_fijos() + casos_azar(a.casos, a.semilla)
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / "core.js").write_text(core.group(1), encoding="utf-8")
        (pathlib.Path(tmp) / "runner.js").write_text(RUNNER, encoding="utf-8")
        entrada = json.dumps([{"b64": base64.b64encode(c["b"]).decode(), "sep": c["sep"],
                               "completo": c.get("completo", False)} for c in casos])
        proc = subprocess.run(["node", str(pathlib.Path(tmp) / "runner.js"), str(pathlib.Path(tmp) / "core.js")],
                              input=entrada, capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit("Node fallo:\n" + proc.stderr)
    resultados = json.loads(proc.stdout)

    fallas, omitidos = [], 0
    for c, r in zip(casos, resultados):
        texto = decodificar(c["b"])
        if r["texto"] != texto:
            fallas.append((c["nombre"], "el texto decodificado no coincide"))
            continue
        try:
            esperado = filas_python(texto, r["sep"])
        except csv.Error:
            omitidos += 1                            # Python tampoco lo acepta
            continue
        if r["filas"] != esperado:
            fallas.append((c["nombre"], f"navegador {r['filas']!r}  python {esperado!r}"))

    # Camino completo sobre ejemplo.csv
    ej = next(r for c, r in zip(casos, resultados) if c.get("completo"))
    filas = filas_python(decodificar(EJEMPLO.read_bytes()), ej["sep"])
    enc, datos = filas[0], filas[1:]
    if ej["revision"]["errores"]:
        fallas.append(("ejemplo.csv", f"la revision marco errores: {ej['revision']['errores']}"))
    for modo, m in ej["modos"].items():
        juntas = [o for t in m["textos"] for o in json.loads(t)]
        if [list(o.keys()) for o in juntas] != [enc] * len(datos):
            fallas.append((f"ejemplo.csv/{modo}", "las llaves no son los encabezados exactos"))
        if [list(o.values()) for o in juntas] != datos:
            fallas.append((f"ejemplo.csv/{modo}", "los valores no son el texto exacto del CSV"))
        malos = [txt for txt, ok, _ in m["checks"] if not ok]
        if malos:
            fallas.append((f"ejemplo.csv/{modo}", f"verificar() fallo: {malos}"))

    print(f"  casos      : {len(casos)} ({len(casos_fijos())} fijos + {a.casos} al azar, semilla {a.semilla})")
    print(f"  omitidos   : {omitidos} (texto que tampoco acepta el modulo csv de Python)")
    print(f"  ejemplo.csv: {len(datos)} filas x {len(enc)} columnas, modos "
          + ", ".join(f"{k} ({v['partes']} parte/s)" for k, v in ej["modos"].items()))
    if fallas:
        print(f"\n  FALLAS: {len(fallas)}")
        for nombre, detalle in fallas[:15]:
            print(f"    {nombre}: {detalle}")
        return 1
    print("  ok: mismo resultado que el modulo csv de Python en todos los casos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
