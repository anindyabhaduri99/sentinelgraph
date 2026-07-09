# SentinelGraph

A production-grade, governed agentic AI platform component that enables enterprise
users (portfolio managers, risk teams, operations analysts) to run multi-step,
tool-augmented investment workflows via natural-language chat — with enterprise-
grade identity propagation, layered guardrails, policy-enforced data access,
immutable audit trail, and full observability. Modeled on the class of problem
BlackRock's Intelligence Servicing Platform solves (250K+ tickets/month, growing
~20% YoY) — built local-first, promoted to AWS EKS.

## End-to-End Request Flow

## Tech Stack


| Layer                        | Tool                                                                     |
| ---------------------------- | ------------------------------------------------------------------------ |
| Orchestration                | LangGraph                                                                |
| LLMs                         | Anthropic Claude + OpenAI GPT — role-driven via Model Gateway            |
| Retrieval                    | LlamaIndex + Chroma (local) → OpenSearch (prod)                          |
| Object storage / audit trail | MinIO (local) → S3 (prod)                                                |
| Relational state             | PostgreSQL — 3 schemas: `ticketing`, `langgraph_checkpoints`, `identity` |
| Governance                   | Custom DAL + PEP                                                         |
| Auth                         | OAuth2 + JWT, token propagation across agent hops                        |
| Guardrails                   | Input / tool-call / output — 3 distinct layers                           |
| Observability                | LangSmith (tracing) + Prometheus + Grafana (metrics)                     |
| Deployment                   | Docker Compose (local) → AWS EKS via CloudFormation                      |




## Docker Compose Services


| Service    | Purpose                                                 |
| ---------- | ------------------------------------------------------- |
| postgres   | ticketing / checkpointer / identity schemas             |
| chroma     | doc chunk embeddings + conversation-turn embeddings     |
| minio      | raw PDF storage + immutable audit trail (S3-compatible) |
| prometheus | metrics scraping                                        |
| grafana    | dashboards                                              |




## Model Gateway

Single abstraction (`get_llm(role)`) centralizing API keys (Anthropic + OpenAI) and
role-based routing:

- Planner/Retriever → light model
- Analyst → reasoning-heavy model
- Evaluator → **cross-family** from Analyst (decorrelation, not cost optimization —
per-call cost/latency is roughly neutral across providers; the benefit is
independent failure modes + rate-limit isolation, at the cost of no shared
prompt-caching and extra vendor operational overhead)



## Guardrail Layers (3 distinct stages — not one generic filter)

1. **Input** — PII detection, prompt-injection pattern scan, request schema validation
2. **Tool-call** — parameter completeness/type validation, blank/error response detection
3. **Output** — PII redaction, risk/compliance disclaimer enforcement, factual-groundedness check



## Evaluation Loop

Evaluator (cross-family LLM judge) scores confidence 0-1. Threshold 0.9:

- ≥ 0.9 → pass to user (with disclaimer if financial recommendation)
- < 0.9 → optimizer node rewrites prompt → retry (max 3 attempts)
- exhausted retries → human-in-the-loop escalation queue



## Ingestion Pipeline (Phase 2)

Synthetic PDFs (fictional fund prospectus, client FAQ, compliance policy) →
uploaded to MinIO → chunked → embedded → indexed in Chroma. Fully synthetic
content — no real BlackRock/Aladdin material used, to avoid IP/confidentiality issues.

## Conversation Memory

Each user turn + agent response is embedded and stored in Chroma alongside
document chunks, enabling semantic recall of prior turns in the same session
(distinct namespace/metadata filter from document chunks).

## Audit Trail (MinIO)

Every request writes one immutable JSON record: input, generated plan, tool
calls + guardrail results at each stage, final output, confidence score,
timestamps. This is the concrete mechanism for proving routing decisions were
deterministic months later — directly answers the "regulatory replay" requirement.

## Fake/Mock External APIs

`services/retriever/mock_apis.py` — simulated Portfolio API and Trade API with
canned/randomized JSON, invoked through the same tool-call + guardrail pattern
as a real API integration would use.

## PostgreSQL — 3-Schema Topology


| Schema                  | Purpose                              | Owner        |
| ----------------------- | ------------------------------------ | ------------ |
| `ticketing`             | business ticket state                | orchestrator |
| `langgraph_checkpoints` | agent execution state (replay/audit) | orchestrator |
| `identity`              | user/session/JWT entitlement cache   | governance   |




## Secrets Management

- Local: `.env` (gitignored) + `.env.example` (committed template)
- Prod (EKS): AWS Secrets Manager + External Secrets Operator + IRSA, no `.env` in image



## Git Conventions

Branches: `main` ← `develop` ← `feature/*`. Commits: Conventional Commits.

## Build Phases

- [x] Phase 0: Repo bootstrap, secrets strategy, git
- [x] Phase 1: Docker Compose — Postgres (3-schema) + Chroma
- [ ] Phase 2: MinIO + PDF ingestion → chunk → embed pipeline (NEXT)
- [ ] Phase 3: Model Gateway implementation
- [ ] Phase 4: LangGraph orchestrator (planner → retriever → analyst → evaluator)
- [ ] Phase 5: Guardrails (input / tool-call / output, 3 distinct layers)
- [ ] Phase 6: Conversation memory embedding + semantic recall
- [ ] Phase 7: Mock external APIs (Portfolio, Trade)
- [ ] Phase 8: MinIO audit trail writer
- [ ] Phase 9: DAL + PEP (identity propagation, token handling across hops)
- [ ] Phase 10: Observability (LangSmith + Prometheus + Grafana)
- [ ] Phase 11: AWS EKS deployment (CloudFormation, IRSA, HPA)

## Phase 2: Model Gateway (mimics AWS Bedrock unified model access)

### Why a separate microservice, not a shared function
Only `model-gateway` container holds ANTHROPIC_API_KEY / OPENAI_API_KEY. Every
other service calls `POST http://model-gateway:8080/invoke` with a role name —
no other service ever sees a provider API key. Network isolation enforces this
boundary in a way a shared Python import cannot. Mirrors AWS Bedrock: nobody
calls Anthropic/OpenAI directly; everybody calls the gateway.

### Endpoint
`POST /invoke` — body: `{role, system_prompt, user_message}` → returns
`{role, provider, model, content}`

### Role -> Model routing (services/model_gateway/router.py)
| Role | Provider | Model | Rationale |
|---|---|---|---|
| planner | anthropic | claude-haiku-4-5 | lightweight, structured plan output |
| retriever | anthropic | claude-haiku-4-5 | tool-selection, not reasoning-heavy |
| analyst | anthropic | claude-sonnet-4-5 | reasoning-heavy, grounded synthesis |
| evaluator | openai | gpt-4o | cross-family, decorrelated judge |
| optimizer | openai | gpt-4o-mini | lightweight prompt-rewrite on retry |

### Prompt Injection Defense
Every system prompt (shared/prompts/*.yml) includes a shared
`injection_defense_block`: treats all user/tool/document content as data not
instructions, refuses to reveal system prompts, refuses role/instruction
override attempts regardless of claimed authority.
**Honest limitation:** this is a first layer only — doesn't stop obfuscated
injection (encoded payloads, indirect injection via tool output). Must be
paired with input guardrail pattern-scanning (Phase 4) and the principle that
the LLM itself never has unmediated write/execute access.

### Secrets
- Local: `model-gateway` container reads keys via `env_file: .env`
- Prod (EKS): only this service's pod has an IRSA role permitted to read
  Secrets Manager for model API keys — every other pod has zero such permission

### How to run
```bash
docker compose up -d --build model-gateway
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{"role":"planner","system_prompt":"You are a planning agent.","user_message":"Summarize AAPL Q3 performance"}'
```

## Build Phases
- [x] Phase 0: Repo bootstrap, secrets strategy, git
- [x] Phase 1: Docker Compose — Postgres (3-schema) + Chroma
- [x] Phase 2: Model Gateway (unified LLM access, mimics Bedrock)
- [ ] Phase 3: Basic LangGraph orchestrator (planner → mock retriever → analyst → evaluator) (NEXT)
- [ ] Phase 4: Basic guardrails (input/output) on the simple graph
- [ ] Phase 5: Vector DB + RAG (Chroma, replacing mock retriever)
- [ ] Phase 6: Conversation memory embedding + semantic recall
- [ ] Phase 7: MinIO document ingestion pipeline
- [ ] Phase 8: MinIO audit trail
- [ ] Phase 9: DAL + PEP (identity propagation, token handling)
- [ ] Phase 10: Observability (LangSmith + Prometheus + Grafana)
- [ ] Phase 11: AWS EKS deployment (CloudFormation, IRSA, HPA)