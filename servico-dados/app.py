from flask import Flask, jsonify, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Métrica do Prometheus: conta as requisições por rota
REQUISICOES = Counter(
    "dados_requisicoes_total",
    "Total de requisicoes recebidas pelo servico de dados",
    ["rota"],
)

PRODUTOS = [
    {"id": 1, "nome": "Notebook", "preco": 3500.00},
    {"id": 2, "nome": "Mouse", "preco": 80.00},
    {"id": 3, "nome": "Teclado", "preco": 150.00},
]


@app.route("/dados")
def dados():
    REQUISICOES.labels(rota="/dados").inc()
    return jsonify({"servico": "servico-dados", "produtos": PRODUTOS})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)