import json
import logging
import os
import threading
import time
from logging.handlers import RotatingFileHandler

import requests
from flask import Flask, jsonify, Response

# --- Configuracao (vem de variaveis de ambiente no Kubernetes) ---
BUFFER_DIR = os.getenv("BUFFER_DIR", "/buffer")
DADOS_URL = os.getenv("DADOS_URL", "http://servico-dados.cloudnative-u4:5000")
TIMEOUT = float(os.getenv("DADOS_TIMEOUT", "2"))

CACHE_FILE = os.path.join(BUFFER_DIR, "cache.json")
EVENTOS_FILE = os.path.join(BUFFER_DIR, "eventos.jsonl")
LOG_FILE = os.path.join(BUFFER_DIR, "edge.log")

os.makedirs(BUFFER_DIR, exist_ok=True)

# --- Log rotativo local (observabilidade parcial que funciona offline) ---
log = logging.getLogger("edge")
log.setLevel(logging.INFO)
arquivo = RotatingFileHandler(LOG_FILE, maxBytes=100_000, backupCount=3)
arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(arquivo)
log.addHandler(logging.StreamHandler())  # tambem aparece no kubectl logs

app = Flask(__name__)
lock = threading.Lock()


def registrar_evento(origem, status):
    """Guarda o evento no buffer local; o script de sincronizacao envia depois."""
    evento = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "no": os.getenv("HOSTNAME", "edge"),
        "rota": "/cliente",
        "origem": origem,
        "status": status,
    }
    with lock:
        with open(EVENTOS_FILE, "a") as f:
            f.write(json.dumps(evento) + "\n")
    log.info("evento registrado: %s", evento)


def salvar_cache(produtos):
    with lock:
        with open(CACHE_FILE, "w") as f:
            json.dump(produtos, f)


def ler_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def formatar(produtos, origem):
    linhas = [f"{p['nome']}: R$ {p['preco']:.2f}" for p in produtos]
    return f"Catalogo de produtos (origem: {origem})\n" + "\n".join(linhas) + "\n"


@app.route("/cliente")
def cliente():
    try:
        resposta = requests.get(f"{DADOS_URL}/dados", timeout=TIMEOUT)
        resposta.raise_for_status()
        produtos = resposta.json()["produtos"]
        salvar_cache(produtos)
        registrar_evento("central", 200)
        return Response(formatar(produtos, "central"), mimetype="text/plain")
    except requests.RequestException as erro:
        log.warning("central indisponivel: %s", erro)
        produtos = ler_cache()
        if produtos is None:
            registrar_evento("indisponivel", 503)
            return jsonify({"erro": "sem conexao com a central e sem cache local"}), 503
        registrar_evento("cache-local", 200)
        return Response(formatar(produtos, "cache-local (offline)"), mimetype="text/plain")


@app.route("/health")
def health():
    # Liveness: o processo esta vivo. Nao depende da central.
    return jsonify({"status": "ok"})


@app.route("/ready")
def ready():
    # Readiness: so verifica o armazenamento local. Offline continua pronto.
    if os.access(BUFFER_DIR, os.W_OK):
        return jsonify({"status": "pronto"})
    return jsonify({"status": "sem-armazenamento"}), 503


@app.route("/status")
def status():
    try:
        with open(EVENTOS_FILE) as f:
            pendentes = sum(1 for _ in f)
    except FileNotFoundError:
        pendentes = 0
    return jsonify({"eventos_pendentes": pendentes, "cache_local": os.path.exists(CACHE_FILE)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)