---
name: appinsights-query
description: Query Azure Application Insights for logs, traces, and exceptions using az CLI or MCP pipeline-copilot
---

# AppInsights Query Workflow

Standard procedure for querying Azure Application Insights to diagnose issues, check logs, and monitor service health.

## When to use

- User asks to "check the logs" or "what's happening in AppInsights"
- Diagnosing service errors or performance issues
- Monitoring specific service behavior over time
- User asks about exceptions, traces, or request failures

## Two approaches

### Approach A: az CLI (for structured queries)

```bash
az monitor app-insights query \
  --app ai-inventory-ingestion \
  --resource-group rg-inventory-ally-brain \
  --analytics-query "traces
    | where timestamp > ago(24h)
    | where cloud_RoleName == 'evc-prod-eqoh'
    | where message has 'ERROR'
    | order by timestamp desc
    | take 50"
```

Common app names:
- `ai-inventory-ingestion` — Main ingestion service
- `evc-prod-app` — Production app
- `ai-inventory-brain` — Brain/MCP service

### Approach B: MCP pipeline-copilot (for quick queries)

Use the `pipeline-copilot` MCP tool `appinsights_query`:

```
service: evc-prod-app
query: traces | where timestamp > ago(12h) | where message has "ERROR" | take 20
```

Or `appinsights_traces` for pre-built trace queries.

### Approach C: List available apps

```bash
az monitor app-insights component list \
  --resource-group rg-inventory-ally-brain \
  --query "[].{name:name, key:InstrumentationKey}"
```

## Common query patterns

### Recent errors

```kusto
traces
| where timestamp > ago(24h)
| where severityLevel >= 2
| order by timestamp desc
| take 50
```

### Request failures

```kusto
requests
| where timestamp > ago(24h)
| where success == false
| order by timestamp desc
| take 30
```

### Performance slow requests

```kusto
requests
| where timestamp > ago(24h)
| where duration > 5s
| order by duration desc
| take 20
```

### Specific service role

```kusto
traces
| where timestamp > ago(12h)
| where cloud_RoleName == "evc-prod-eqoh"
| where message has "Instinct"
| order by timestamp desc
```

## Gotches

- `timestamp` is in UTC — convert local times accordingly
- `ago()` uses UTC hours — `ago(24h)` = last 24 hours UTC
- `cloud_RoleName` is case-sensitive
- az CLI queries may time out for large result sets — add `| take` to limit
- MCP `appinsights_query` has a shorter timeout than az CLI
