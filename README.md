# DevOps II - Unidade 4: Microsserviços Cloud-Native

Integração de microsserviços com Kubernetes e arquitetura cloud-native: deploy automatizado, observabilidade (métricas e tracing) e simulação de execução na borda (edge).

## Visão geral

| Passo | O que foi feito |
|---|---|
| 1 | Dois microsserviços Flask em containers, manifestos Kubernetes e pipeline GitHub Actions (build, push e deploy) |
| 2 | Métricas Prometheus, tracing distribuído com OpenTelemetry e Jaeger |
| 3 | Nó de borda com cache local, buffer offline, sondas tolerantes e sincronização com a central |

## Estrutura do repositório

```
.github/workflows/deploy.yml     pipeline CI/CD
servico-dados/                   microsserviço que retorna os dados (GET /dados)
servico-cliente/                 microsserviço que consome e formata (GET /cliente)
edge/servico-cliente-edge/       versão do cliente para a borda (cache, buffer, log rotativo)
central/central-receiver/        receptor da central para a sincronização
k8s/                             manifestos dos serviços (kustomize)
k8s/observabilidade/             Prometheus e Jaeger
k8s/edge/                        nó de borda, receptor da central e CronJob de sincronização
```

## Imagens (Docker Hub, usuário michelazevedo)

- `u4-servico-dados:v3` e `u4-servico-cliente:v3`
- `u4-servico-cliente-edge:v1` e `u4-central-receiver:v1`

## Passo 1: microsserviços e pipeline

- `servico-dados` retorna uma lista de produtos em JSON; `servico-cliente` chama o serviço de dados pelo nome do Service (DNS interno) e devolve um texto formatado.
- Manifestos no namespace `cloudnative-u4`: `Deployment` com 2 réplicas, `requests` e `limits` de recursos, labels e selectors organizados, sondas `/health` e `Service` do tipo `ClusterIP`.
- O workflow `deploy.yml` roda a cada push na `main` e tem dois jobs:
  1. `build-push`: constrói as duas imagens (matriz por serviço) e publica no Docker Hub com a tag `v3` e a tag do commit.
  2. `deploy`: cria um cluster temporário (kind), troca a tag nos manifestos pela do commit, aplica com `kubectl apply -k k8s`, espera o rollout e testa o `/cliente`.
- Credenciais do Docker Hub ficam nos secrets do repositório (`DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN`).
- O cluster do pipeline é temporário porque o GitHub Actions não alcança o Minikube local.

## Passo 2: observabilidade

- **Métricas:** os dois serviços expõem `/metrics` (biblioteca `prometheus_client`) com contadores de requisições e histogramas de latência (`dados_latencia_segundos` e `cliente_latencia_segundos`).
- **Prometheus** (namespace `observabilidade-u4`): descobre os pods pela API do Kubernetes e coleta apenas os que têm a annotation `prometheus.io/scrape: "true"`. Acesso por `kubectl port-forward`.
- **Tracing:** instrumentação com OpenTelemetry (Flask e requests). O contexto do trace atravessa a chamada HTTP entre os serviços, então uma requisição aparece como um único trace com os dois serviços.
- **Jaeger v2** recebe os spans por OTLP/HTTP (porta 4318). O Jaeger v1 e o agent chegaram ao fim de vida; no v2 os serviços enviam direto ao coletor, sem sidecar de agent.
- Os spans `consultar-produtos` (pausa de 50 ms que simula uma consulta a banco) e `formatar-resposta` deixam as etapas visíveis no trace.
- As sondas `/health` e `/metrics` foram excluídas do tracing para não poluir o Jaeger.

## Passo 3: simulação de borda (edge)

O nó de borda roda o `servico-cliente-edge` no namespace `edge-u4`, separado da central (`cloudnative-u4`).

- **Cache local:** a cada resposta bem-sucedida da central, o serviço grava os dados em `/buffer/cache.json`. Se a central ficar fora do ar, responde com o cache (`origem: cache-local (offline)`).
- **Buffer local:** um `PersistentVolumeClaim` de 100 Mi guarda o cache, os eventos pendentes (`eventos.jsonl`) e o log rotativo (`edge.log`, 100 KB por arquivo e 3 arquivos de histórico).
- **Observabilidade parcial offline:** log rotativo local, que continua gravando sem conexão (opção ao Push Gateway).
- **Sondas tolerantes:** liveness em `/health` (a cada 20 s, timeout de 5 s, 5 falhas) e readiness em `/ready` (a cada 10 s, timeout de 5 s, 6 falhas). Nenhuma delas depende da central, senão o nó sairia do ar justamente quando ficasse offline.
- **NetworkPolicy** `edge-restritiva`: só recebe tráfego interno e só sai para o DNS do cluster e para a central (porta 5000).
- **Sincronização:** o `CronJob edge-sync` (suspenso, disparado manualmente) congela o buffer, envia os eventos ao `central-receiver` e, se a central estiver fora, devolve tudo ao buffer. Nenhum evento é perdido.

### Como simular offline e sincronizar

```
# derrubar a central
kubectl scale deployment servico-dados central-receiver -n cloudnative-u4 --replicas=0
curl.exe http://localhost:8082/cliente        # responde com o cache local
curl.exe http://localhost:8082/status         # eventos_pendentes cresce

# tentar sincronizar (falha, eventos permanecem no buffer)
kubectl create job sync-offline --from=cronjob/edge-sync -n edge-u4

# religar a central e sincronizar
kubectl scale deployment servico-dados -n cloudnative-u4 --replicas=2
kubectl scale deployment central-receiver -n cloudnative-u4 --replicas=1
kubectl create job sync-online --from=cronjob/edge-sync -n edge-u4
```

## Como executar

```
minikube start -p u4
kubectl apply -k k8s
kubectl apply -k k8s/observabilidade
kubectl apply -k k8s/edge
```

## Limitações e decisões

- O CNI `bridge` do Minikube não aplica `NetworkPolicy`; o manifesto declara o isolamento, e o offline é simulado derrubando a central.
- O `central-receiver` guarda os eventos em memória (apenas demonstração).
- As imagens da borda e do receptor foram publicadas manualmente; o pipeline cobre os dois serviços originais.
- O Prometheus usa armazenamento temporário com retenção de 2 horas, suficiente para o laboratório.
- A latência de 50 ms no serviço de dados é simulada para que o trace tenha etapas visíveis.