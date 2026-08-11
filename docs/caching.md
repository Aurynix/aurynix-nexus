# Caching

Aurynix uses Redis to cache LLM responses and expensive computations, reducing latency for repeated queries and cutting API costs.

---

## LLM Response Cache

Identical questions with identical context get the same answer — there is no value in calling Groq twice.

### Cache key

```
llm_cache:{sha256(model + messages_json + tools_json)}
```

The key is a SHA-256 hash of:
- Model name (`llama-3.3-70b-versatile`)
- Serialized message history (all messages in the current turn)
- Tool list (so adding a new tool invalidates cached entries)

### Cache flow

```
Agent node prepares LLM call
        │
Compute cache key
        │
GET llm_cache:{key}  →  hit?
  ├── Yes → return cached AIMessage (skip Groq call)
  └── No  → call Groq
              │
              ▼
         Cache result (TTL = LLM_CACHE_TTL_SECONDS)
              │
              ▼
         Return AIMessage
```

### Configuration

```bash
LLM_CACHE_ENABLED=true       # set false to disable entirely
LLM_CACHE_TTL_SECONDS=300    # 5 minutes default
LLM_CACHE_MAX_SIZE_KB=512    # skip caching responses larger than this
```

### What is NOT cached

- Streaming responses (the cache stores and replays the full assembled response)
- Calls where `temperature > 0` and `CACHE_NONDETERMINISTIC=false` (default: skip caching when temperature > 0 to avoid stale creative responses)
- Tool call results (those depend on live data)
- Any request that contains `"no-cache": true` in the SSE metadata payload

---

## Embedding Cache

Computing embeddings for the same text repeatedly is wasteful. `FastEmbedEmbedder` caches embedding vectors in Redis:

```
embed_cache:{sha256(model_name + text)}  →  JSON float array
```

```bash
EMBED_CACHE_ENABLED=true
EMBED_CACHE_TTL_SECONDS=86400   # 24 hours — embeddings rarely change
```

This matters most during RAG ingestion of large documents where many chunks share overlapping text (e.g., headers repeated across pages).

---

## Conversation Summary Cache

When a conversation exceeds `HISTORY_WINDOW` messages, Aurynix summarizes older turns instead of including them verbatim. Summaries are cached so they are not regenerated on every request:

```
conv_summary:{conversation_id}:{message_count}  →  summary string
```

TTL: `SUMMARY_CACHE_TTL_SECONDS` (default: 3600).

---

## Manual Cache Invalidation

```bash
# Flush all LLM cache entries
redis-cli --scan --pattern "llm_cache:*" | xargs redis-cli del

# Flush embed cache
redis-cli --scan --pattern "embed_cache:*" | xargs redis-cli del

# Flush a specific conversation summary
redis-cli del "conv_summary:{conversation_id}:*"
```

Or via the admin endpoint (requires `X-Admin-Token`):

```bash
DELETE /api/v1/admin/cache?pattern=llm_cache
DELETE /api/v1/admin/cache?pattern=embed_cache
```

---

## Cache Observability

Cache hits and misses are exported as Prometheus counters:

```
aurynix_cache_hits_total{cache="llm"}
aurynix_cache_misses_total{cache="llm"}
aurynix_cache_hits_total{cache="embed"}
aurynix_cache_misses_total{cache="embed"}
```

Hit rate is visible in the Grafana dashboard under **Cache Performance**.

See [Observability](observability.md) for metrics setup.
