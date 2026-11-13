import os

import requests
from flask import Flask, jsonify, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# --- OpenTelemetry: envia os traces para o Jaeger via OTLP/HTTP ---
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger.observabilidade-u4:4318")
provider = TracerProvider(resource=Resource.create({"service.name": "servico-cliente"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP_ENDPOINT}/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("servico-cliente")

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app, excluded_urls="health,metrics")
# Faz o trace "atravessar" a chamada HTTP para o servico-dados
RequestsInstrumentor().instrument()

# Endereco do servico-dados. No Kubernetes, o nome do Service funciona como DNS.
DADOS_URL = os.getenv("DADOS_URL", "http://servico-dados:5000")

REQUISICOES = Counter(
    "cliente_requisicoes_total",
    "Total de requisicoes recebidas pelo servico cliente",
    ["rota", "status"],
)
LATENCIA = Histogram(
    "cliente_latencia_segundos",
    "Tempo de resposta do servico cliente",
    ["rota"],
)


@app.route("/cliente")
def cliente():
    with LATENCIA.labels(rota="/cliente").time():
        try:
            resposta = requests.get(f"{DADOS_URL}/dados", timeout=3)
            resposta.raise_for_status()
            produtos = resposta.json()["produtos"]
        except requests.RequestException as erro:
            REQUISICOES.labels(rota="/cliente", status="erro").inc()
            return jsonify({"erro": "servico-dados indisponivel", "detalhe": str(erro)}), 503

        with tracer.start_as_current_span("formatar-resposta"):
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