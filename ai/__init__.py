"""
GoLegal AI / Agent Layer

- llm:                 provider gateway (Anthropic Claude) with offline null client
- tools:               guarded tool registry shared by every agent
- copilot:             conversational assistant (tool-using loop or rule router)
- workflow_agent:      autonomous lifecycle operator (dispatch, remind, expire, seal, purge)
- clause_intelligence: risk scoring, PII redaction, plain-language / vernacular summaries
- rent_benchmark:      fair-rent and deposit norms per micro-market
- contract_ingest:     digitise existing contracts / natural-language briefs into a draft
"""
from ai.clause_intelligence import ClauseIntelligence, RiskFinding, RiskReport, redact_pii
from ai.contract_ingest import IngestResult, extract_terms, extract_text_from_pdf, merge_into_payload
from ai.copilot import Copilot, CopilotReply
from ai.llm import AnthropicLLMClient, LLMClient, LLMResponse, LLMUnavailableError, NullLLMClient, get_llm_client, reset_llm_client
from ai.rent_benchmark import benchmark, supported_cities
from ai.tools import ToolContext, ToolPermissionError, ToolRegistry, build_registry
from ai.workflow_agent import WorkflowAgent

__all__ = [
    "ClauseIntelligence", "RiskFinding", "RiskReport", "redact_pii",
    "IngestResult", "extract_terms", "extract_text_from_pdf", "merge_into_payload",
    "Copilot", "CopilotReply",
    "AnthropicLLMClient", "LLMClient", "LLMResponse", "LLMUnavailableError", "NullLLMClient", "get_llm_client", "reset_llm_client",
    "benchmark", "supported_cities",
    "ToolContext", "ToolPermissionError", "ToolRegistry", "build_registry",
    "WorkflowAgent",
]
