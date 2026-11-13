import logging

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
app = Flask(__name__)

# Eventos recebidos dos nos de borda (guardados em memoria, so para a demonstracao)
recebidos = []


@app.route("/sync", methods=["POST"])
def sync():
    dados = request.get_json(silent=True) or {}
    eventos = dados.get("eventos", [])
    recebidos.extend(eventos)
    logging.info("sincronizacao recebida: %d eventos (total acumulado: %d)", len(eventos), len(recebidos))
    return jsonify({"recebidos": len(eventos), "total": len(recebidos)})


@app.route("/total")
def total():
    return jsonify({"total": len(recebidos), "ultimos": recebidos[-5:]})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)