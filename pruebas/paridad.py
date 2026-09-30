#!/usr/bin/env python3
"""Prueba de paridad: el parser del navegador contra el modulo csv de Python.

La herramienta promete una conversion FIEL. Esta prueba lo comprueba corriendo el
nucleo real (el <script id="core"> de csv-a-json.html, con Node) y el modulo csv
de Python sobre los mismos bytes, y exigiendo el mismo resultado:

  1. las mismas filas, celda por celda;
  2. el mismo numero de fila para cada una (como Excel: encabezado = 1, las
     lineas vacias cuentan), que es el que se muestra en los errores;
  3. comillas sin cerrar: la herramienta las marca exactamente cuando el modo
     estricto de Python dice "unexpected end of data";
  4. casos fijos con resultado conocido: separador detectado, UTF-16, ejemplo.csv
     y una columna llamada __proto__, de punta a punta (objetos -> partes -> JSON
     -> verificar) en los tres modos de salida;
  5. miles de textos al azar armados con los caracteres que rompen un CSV
     (; , " \\r \\n espacio y tildes), con semilla fija para que se repitan.

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
  const r = { texto: d.texto, codif: d.codif, sep, filas: p.filas, vacias: p.vacias,
              numeros: p.numeros, comilla: p.comillaAbierta };
  if (c.completo) {
    const enc = p.filas[0], datos = p.filas.slice(1);
    const objetos = Core.aObjetos(enc, datos);
    r.revision = Core.revisar(enc, datos, p);
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
    if b.startswith(b"\xff\xfe"):
        return b[2:].decode("utf-16-le")
    if b.startswith(b"\xfe\xff"):
        return b[2:].decode("utf-16-be")
    if b.startswith(b"\xef\xbb\xbf"):
        return b[3:].decode("utf-8")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252")


def leer_python(texto, sep):
    """Filas con contenido y su numero de registro. El modulo csv devuelve [] por
    cada linea vacia; la herramienta no las convierte, pero SI las cuenta al
    numerar (como Excel)."""
    todas = list(csv.reader(io.StringIO(texto, newline=""), delimiter=sep))
    return [f for f in todas if f != []], [k for k, f in enumerate(todas, 1) if f != []]


def comilla_abierta_python(texto, sep):
    """True/False si el modo estricto lo sabe; None si falla por otra razon antes."""
    try:
        list(csv.reader(io.StringIO(texto, newline=""), delimiter=sep, strict=True))
        return False
    except csv.Error as e:
        return True if "unexpected end of data" in str(e) else None


def casos_fijos():
    def t(s, separador=";", **espera):
        """separador=None: que lo detecte la herramienta. espera: resultado conocido."""
        return {"nombre": repr(s)[:50], "b": s.encode("utf-8"), "sep": separador, "espera": espera}
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
        t("A;B\n\n1;2\n\n\n3;4\n", numeros=[1, 3, 6]),   # lineas vacias: cuentan al numerar
        t('A;B\n\n\n1;"a\nb\nc"\n2\n', numeros=[1, 4, 5]),
        t("A;B\n  1  ; 2 \n"),                      # espacios: no se recortan
        t("A;B;C\n;;\n"),                           # fila con todas las celdas vacias
        t('A\n""\n'),                               # una sola columna, valor vacio entre comillas
        t('A\n""'),
        t('A;B\n1;"x\n2;y\n', comilla=2),           # comillas sin cerrar: se come el resto
        t("A,B\n1,2\n", ","),
        t("A\tB\n1\t2\n", "\t"),
        # separador detectado solo, contando fuera de comillas
        t('"Nombre, completo";"Ciudad, estado"\nAna;CDMX\n', None, sep=";"),
        t('"a; b","c; d"\n"1; 2","3; 4"\n', None, sep=","),
        t("SKU;NOMBRE\n1;Café\n", None, sep=";"),
        {"nombre": "BOM UTF-8", "b": b"\xef\xbb\xbfA;B\n\xc3\xa1;2\n", "sep": ";", "espera": {}},
        {"nombre": "Windows-1252", "b": "CAMPAÑA;DESCRIPCIÓN\nPiñata;Acción\n".encode("cp1252"),
         "sep": ";", "espera": {"codif": "Windows-1252"}},
        {"nombre": "UTF-16LE (Texto Unicode de Excel)",
         "b": b"\xff\xfe" + "SKU\tNOMBRE\n1\tCafé\n".encode("utf-16-le"),
         "sep": None, "espera": {"sep": "\t", "codif": "UTF-16"}},
        {"nombre": "UTF-16BE", "b": b"\xfe\xff" + "SKU;NOMBRE\n1;Café\n".encode("utf-16-be"),
         "sep": None, "espera": {"sep": ";", "codif": "UTF-16"}},
        {"nombre": "columna __proto__", "b": b"id;__proto__;constructor\n1;x;y\n2;z;w\n",
         "sep": None, "completo": True, "espera": {}},
        {"nombre": "ejemplo.csv", "b": EJEMPLO.read_bytes(), "sep": None, "completo": True, "espera": {}},
    ]


def casos_azar(n, semilla):
    rnd = random.Random(semilla)
    piezas = ["a", "b", "7", "é", "Ñ", " ", ";", ",", '"', '""', "\n", "\r\n", "\r"]
    casos = []
    for i in range(n):
        s = "".join(rnd.choice(piezas) for _ in range(rnd.randint(0, 40)))
        casos.append({"nombre": f"azar #{i}", "b": s.encode("utf-8"), "sep": ";", "espera": {}})
    return casos


def revisar_completo(nombre, r, fallas):
    """Camino completo: objetos -> partes -> JSON -> verificar, en los tres modos."""
    enc, datos = r["filas"][0], r["filas"][1:]
    if r["revision"]["errores"]:
        fallas.append((nombre, f"la revision marco errores: {r['revision']['errores']}"))
    for modo, m in r["modos"].items():
        juntas = [o for t in m["textos"] for o in json.loads(t)]
        if [list(o.keys()) for o in juntas] != [enc] * len(datos):
            fallas.append((f"{nombre}/{modo}", "las llaves no son los encabezados exactos"))
        if [list(o.values()) for o in juntas] != datos:
            fallas.append((f"{nombre}/{modo}", "los valores no son el texto exacto del CSV"))
        malos = [txt for txt, ok, _ in m["checks"] if not ok]
        if malos:
            fallas.append((f"{nombre}/{modo}", f"verificar() fallo: {malos}"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casos", type=int, default=5000, help="textos al azar (default 5000)")
    ap.add_argument("--semilla", type=int, default=1)
    a = ap.parse_args()

    core = re.search(r'<script id="core">(.*?)</script>', FUENTE.read_text(encoding="utf-8"), re.S)
    if not core:
        raise SystemExit("No se encontro <script id=\"core\"> en csv-a-json.html")

    fijos = casos_fijos()
    casos = fijos + casos_azar(a.casos, a.semilla)
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

    fallas, comillas = [], {"marcadas": 0, "sin_referencia": 0}
    for c, r in zip(casos, resultados):
        nombre = c["nombre"]
        texto = decodificar(c["b"])
        if r["texto"] != texto:
            fallas.append((nombre, "el texto decodificado no coincide"))
            continue
        for clave, valor in c["espera"].items():
            if r.get(clave) != valor:
                fallas.append((nombre, f"{clave}: esperado {valor!r}, salio {r.get(clave)!r}"))
        filas, numeros = leer_python(texto, r["sep"])
        if r["filas"] != filas:
            fallas.append((nombre, f"filas: navegador {r['filas']!r}  python {filas!r}"))
        elif r.get("numeros") != numeros:
            fallas.append((nombre, f"numeros de fila: navegador {r.get('numeros')}  python {numeros}"))
        abierta = comilla_abierta_python(texto, r["sep"])
        if abierta is None:
            comillas["sin_referencia"] += 1
        elif abierta != bool(r.get("comilla")):
            fallas.append((nombre, f"comillas sin cerrar: navegador {r.get('comilla')}  python {abierta}"))
        comillas["marcadas"] += bool(r.get("comilla"))
        if c.get("completo"):
            revisar_completo(nombre, r, fallas)

    ej = resultados[len(fijos) - 1]
    print(f"  casos      : {len(casos)} ({len(fijos)} fijos + {a.casos} al azar, semilla {a.semilla})")
    print(f"  comillas   : {comillas['marcadas']} casos con comillas sin cerrar, todos confirmados por Python estricto"
          f" ({comillas['sin_referencia']} sin referencia: Python estricto falla antes por otra razon)")
    print(f"  ejemplo.csv: {len(ej['filas']) - 1} filas x {len(ej['filas'][0])} columnas, modos "
          + ", ".join(f"{k} ({v['partes']} parte/s)" for k, v in ej["modos"].items()))
    if fallas:
        print(f"\n  FALLAS: {len(fallas)}")
        for nombre, detalle in fallas[:15]:
            print(f"    {nombre}: {detalle}")
        return 1
    print("  ok: mismas filas, mismos numeros de fila y mismas comillas abiertas que el modulo csv de Python.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
