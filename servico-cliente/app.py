import os

import requests
from flask import Flask, jsonify, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Endereço do servico-dados. No Kubernetes, o nome do Service funciona como DNS.
DADOS_URL = os.getenv("DADOS_URL", "http://servico-dados:5000")

REQUISICOES = Counter(
    "cliente_requisicoes_total",
    "Total de requisicoes recebidas pelo servico cliente",
    ["rota", "status"],
)


@app.route("/cliente")
def cliente():
    try:
        resposta = requests.get(f"{DADOS_URL}/dados", timeout=3)
        resposta.raise_for_status()
        produtos = resposta.json()["produtos"]
    except requests.RequestException as erro:
        REQUISICOES.labels(rota="/cliente", status="erro").inc()
        return jsonify({"erro": "servico-dados indisponivel", "detalhe": str(erro)}), 503

    linhas = [f"{p['nome']}: R$ {p['preco']:.2f}" for p in produtos]
    REQUISICOES.labels(rota="/cliente", status="ok").inc()
    return Response("Catalogo de produtos\n" + "\n".join(linhas) + "\n", mimetype="text/plain")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)