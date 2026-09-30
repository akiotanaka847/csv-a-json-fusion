#!/usr/bin/env python3
"""Arma la carpeta para Netlify a partir de csv-a-json.html.

La fuente es UN archivo HTML (se abre con doble clic, funciona sin internet).
Para publicarlo se separa en archivos porque la politica de seguridad (CSP) que
se manda desde Netlify es estricta: `script-src 'self'` y `style-src 'self'`
bloquean el codigo y los estilos escritos dentro del HTML. Separarlos permite esa
politica sin tener que abrirla con 'unsafe-inline'.

    csv-a-json.html  ->  dist/index.html + estilo.css + core.js + ui.js
                         + _headers + netlify.toml

El contenido no se toca: se corta y se pega. La compuerta del final verifica que
no haya quedado nada en linea y que core/ui sean identicos a la fuente; si algo
falla, borra la carpeta para que no se publique a medias.

Uso:
    python3 build_netlify.py              # -> dist/
    python3 build_netlify.py --out DIR
"""

import argparse
import pathlib
import re
import shutil

AQUI = pathlib.Path(__file__).resolve().parent
FUENTE = AQUI / "csv-a-json.html"

# La herramienta no pide nada a la red: todo sale del mismo origen. No se embebe en
# ningun otro sitio (frame-ancestors 'none'), y blob: es para las descargas.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")
CABECERAS = [
    ("Content-Security-Policy", CSP + "; frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    # Herramienta interna: que no aparezca en buscadores.
    ("X-Robots-Tag", "noindex, nofollow"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
]


def extraer(html):
    estilo = re.search(r"<style>(.*?)</style>", html, re.S)
    core = re.search(r'<script id="core">(.*?)</script>', html, re.S)
    ui = re.search(r"</script>\s*<script>(.*?)</script>", html, re.S)
    if not (estilo and core and ui):
        raise SystemExit("No se encontraron <style>, <script id=\"core\"> y el <script> de la interfaz.")
    return estilo, core, ui


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(AQUI / "dist"))
    a = ap.parse_args()

    html = FUENTE.read_text(encoding="utf-8")
    estilo, core, ui = extraer(html)

    nuevo = html
    nuevo = nuevo.replace(ui.group(0), '</script>\n<script src="ui.js"></script>', 1)
    nuevo = nuevo.replace(core.group(0), '<script src="core.js"></script>', 1)
    nuevo = nuevo.replace(estilo.group(0), '<link rel="stylesheet" href="estilo.css">', 1)
    # La misma CSP en un <meta>, para que probarlo en local se comporte igual que en
    # Netlify (frame-ancestors no aplica en <meta>; va solo en la cabecera).
    nuevo = nuevo.replace('<meta name="viewport"',
                          f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n<meta name="viewport"', 1)
    # El reemplazo de `ui` deja un </script> huerfano delante: se limpia.
    nuevo = nuevo.replace('<script src="core.js"></script></script>\n', '<script src="core.js"></script>\n', 1)

    destino = pathlib.Path(a.out)
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    (destino / "index.html").write_text(nuevo, encoding="utf-8")
    (destino / "estilo.css").write_text(estilo.group(1).strip() + "\n", encoding="utf-8")
    (destino / "core.js").write_text(core.group(1).strip() + "\n", encoding="utf-8")
    (destino / "ui.js").write_text(ui.group(1).strip() + "\n", encoding="utf-8")
    (destino / "_headers").write_text(
        "# Generado por build_netlify.py -- no editar a mano.\n/*\n"
        + "".join(f"  {k}: {v}\n" for k, v in CABECERAS), encoding="utf-8")
    (destino / "netlify.toml").write_text(
        '# Generado por build_netlify.py -- no editar a mano.\n[build]\n  publish = "."\n\n'
        '[[headers]]\n  for = "/*"\n  [headers.values]\n'
        + "".join(f'    {k} = "{v}"\n' for k, v in CABECERAS), encoding="utf-8")

    # Compuerta: nada en linea, y el codigo publicado es el mismo que la fuente.
    idx = (destino / "index.html").read_text(encoding="utf-8")
    problemas = []
    if re.search(r"<script(?![^>]*\bsrc=)[^>]*>", idx):
        problemas.append("queda un <script> en linea")
    if "<style" in idx or re.search(r'\sstyle="', idx):
        problemas.append("queda un estilo en linea")
    if re.search(r"\son[a-z]+=", idx):
        problemas.append("queda un manejador on...= en linea")
    for f in ("estilo.css", "core.js", "ui.js"):
        if f not in idx:
            problemas.append(f"index.html no referencia {f}")
    if (destino / "core.js").read_text(encoding="utf-8").strip() != core.group(1).strip():
        problemas.append("core.js difiere de la fuente")
    if (destino / "ui.js").read_text(encoding="utf-8").strip() != ui.group(1).strip():
        problemas.append("ui.js difiere de la fuente")
    if problemas:
        shutil.rmtree(destino)
        raise SystemExit("FALLA: " + "; ".join(problemas) + ". Se borro la carpeta.")

    print(f"  {destino}")
    for f in sorted(destino.iterdir()):
        print(f"    {f.name:<14} {f.stat().st_size / 1024:6.1f} KB")
    print("  ok: sin codigo ni estilos en linea; CSP estricta en _headers, netlify.toml y <meta>.")


if __name__ == "__main__":
    raise SystemExit(main())
