"""Open the isolated static demonstration on this computer; no services required."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

parser = argparse.ArgumentParser(description="Prévia local da demonstração Tapioca Valley")
parser.add_argument("--no-browser", action="store_true", help="Mostrar URL sem abrir navegador")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
handler = partial(SimpleHTTPRequestHandler, directory=str(root))
with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
    url = f"http://127.0.0.1:{server.server_port}/prototypes/index.html"
    print(f"Prévia local: {url}\nEncerre com Ctrl+C. Sem merge, deploy ou conexão externa.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
