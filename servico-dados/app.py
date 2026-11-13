import os
import time

from flask import Flask, jsonify, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# --- OpenTelemetry: envia os traces para o Jaeger via OTLP/HTTP ---
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger.observabilidade-u4:4318")
provider = TracerProvider(resource=Resource.create({"service.name": "servico-dados"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{OTLP_ENDPOINT}/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("servico-dados")

app = Flask(__name__)
# /health e /metrics ficam fora dos traces para nao poluir o Jaeger com as probes
FlaskInstrumentor().instrument_app(app, excluded_urls="health,metrics")

# --- Metricas Prometheus ---
REQUISICOES = Counter(
    "dados_requisicoes_total",
    "Total de requisicoes recebidas pelo servico de dados",
    ["rota"],
)
LATENCIA = Histogram(
    "dados_latencia_segundos",
    "Tempo de resposta do servico de dados",
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
    with LATENCIA.labels(rota="/dados").time():
        # Span proprio que representa uma consulta a um banco (simulada)
        with tracer.start_as_current_span("consultar-produtos"):
            time.sleep(0.05)
        return jsonify({"servico": "servico-dados", "produtos": PRODUTOS})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)