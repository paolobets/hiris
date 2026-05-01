# HIRIS — Full Local Mode (Zero Cloud)

> Version: 0.8.5 · Updated: 2026-05-01

Run HIRIS with no cloud dependencies: all AI inference, embeddings, and data stay on your local network.

---

## Overview

HIRIS supports a fully offline operating mode. When configured with a local Ollama instance and a local embedding provider (model2vec), every component runs on your hardware:

| Component | Local option |
|-----------|-------------|
| AI reasoning (agentic loop) | Ollama |
| Semantic entity classification | Ollama (same instance) |
| Memory & RAG embeddings | model2vec (in-process, no server) |
| Home Assistant integration | HA WebSocket / REST (always local) |
| Weather forecasts | Open-Meteo (free, no key needed) |

No API keys are required. No data leaves your home network.

---

## Prerequisites

- **Ollama** installed and reachable from the HIRIS add-on
  - Ollama must be on the same local network as Home Assistant (or on the same host)
  - Default port: `11434`
  - Verify with: `curl http://<ollama-host>:11434/api/tags`
- **A capable model pulled in Ollama** (see [Choosing a model](#choosing-a-model) below)
- HIRIS add-on v0.6.x or later

---

## Choosing a model

The agentic loop makes demands that differ from simple chat: the model must reliably produce structured tool-call JSON, follow multi-step instructions, and maintain context across several tool iterations.

### Primary recommendation — Qwen2.5:27b (24 GB+ VRAM / RAM)

```bash
ollama pull qwen2.5:27b
```

Qwen 2.5 27B is the strongest open model for tool use and structured output. It handles Italian well and has a 128 k context window.

| Property | Value |
|----------|-------|
| RAM required | ~18 GB (Q4_K_M quantisation) |
| Context window | 128 k tokens |
| Tool use reliability | Excellent |
| Italian | Good |
| Tok/s (RTX 3090) | ~25 |

### Alternative — Mistral Small 3.1 (16 GB VRAM / RAM)

```bash
ollama pull mistral-small3.1
```

Mistral Small 3.1 is the best option if Italian language quality is a priority and you have less than 24 GB of GPU/RAM. It has strong multilingual support and good instruction following.

| Property | Value |
|----------|-------|
| RAM required | ~11 GB (Q4_K_M quantisation) |
| Context window | 128 k tokens |
| Tool use reliability | Good |
| Italian | Excellent |
| Tok/s (RTX 3090) | ~40 |

### Lighter options (8 GB VRAM)

These work for simple tasks but tool-call reliability degrades on complex agents:

- `qwen2.5:7b` — good balance, moderate Italian
- `llama3.2:3b` — very fast, limited reasoning depth

---

## Configuration

```yaml
# Ollama for AI inference
local_model:
  url: http://192.168.1.10:11434
  model: qwen2.5:27b            # used as default when an agent has model: auto

# Prefer local backend over cloud when both are configured
llm_strategy: cost_first

# Local embeddings — no server, installs cleanly on Alpine
memory:
  embedding_provider: model2vec
  embedding_model: minishlab/potion-base-8M
  rag_k: 5
  retention_days: 90

# Leave empty — not required for local-only mode
claude_api_key: ""
openai_api_key: ""
```

With `llm_strategy: cost_first`, when an agent has `model: auto` HIRIS routes to Ollama before trying any cloud provider. If no cloud keys are configured, Ollama is the only available backend and routing is automatic regardless of strategy.

---

## Setting the model per agent

In the HIRIS agent designer (Config UI):

1. Open an agent (or create a new one)
2. In the **Model** field, select the Ollama model from the dropdown — it appears under the **Ollama** group once `local_model.url` is configured
3. Save the agent

The model dropdown is populated live from `/api/models`, which queries your Ollama instance for available models. You can mix providers per agent: assign a capable model to chat agents for quality and a lighter, faster model to monitor agents to reduce latency on high-frequency runs.

---

## Expected performance vs Claude

| Aspect | Claude Sonnet 4.6 | Qwen2.5:27b (local) | Mistral Small 3.1 (local) |
|--------|-------------------|---------------------|--------------------------|
| Tool call reliability | Excellent | Good | Good |
| Complex reasoning | Excellent | Good | Moderate |
| Italian language | Excellent | Good | Excellent |
| Latency (first token) | 800–1200 ms | 200–600 ms | 150–400 ms |
| Throughput | 60–80 tok/s | 20–30 tok/s (RTX 3090) | 35–50 tok/s (RTX 3090) |
| Cost per run | ~€0.001–0.01 | Free | Free |
| Context window | 200 k | 128 k | 128 k |

Latency figures for local models assume dedicated GPU inference. CPU-only inference is typically 3–10× slower.

---

## Known limitations

**Tool call JSON reliability:** local models occasionally produce malformed tool-call JSON, especially on smaller models or complex multi-step tasks. HIRIS catches these errors and returns them to the model as a tool error — the loop retries, but complex tasks may take more iterations or fail after the 10-iteration limit.

**Context window saturation:** with `rag_k: 5` and a long conversation history, the effective context can reach 8–15 k tokens. Models below 14B parameters may show quality degradation near this limit.

**No streaming fallback:** if the local model is unavailable (Ollama unreachable), HIRIS will not automatically fall back to a cloud provider unless `claude_api_key` or `openai_api_key` is also configured.

**Entity classification:** the Semantic Home Map uses the same Ollama model for unknown entities. On lighter models this may produce lower-quality labels, but the rule-based classifier handles most common entity types without any LLM assistance.
