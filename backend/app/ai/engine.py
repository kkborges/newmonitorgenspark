"""
Nexus AI Engine — Autonomous AI for analysis, baselines, security and traces.
Supports OpenAI, Anthropic, Gemini (configurable per tenant or globally).
"""
from typing import Optional, Dict, Any, List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class AIEngine:
    """
    Unified AI interface supporting multiple providers.
    Used by all AI workers.
    """

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None):
        self.provider = provider or settings.AI_PROVIDER
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client

        if self.provider == "openai":
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key or settings.OPENAI_API_KEY
            )
        elif self.provider == "anthropic":
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self.api_key or settings.ANTHROPIC_API_KEY
            )
        elif self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key or settings.GEMINI_API_KEY)
            self._client = genai.GenerativeModel(
                self.model or settings.GEMINI_MODEL
            )
        return self._client

    async def complete(self, system_prompt: str, user_prompt: str,
                       temperature: float = 0.3, max_tokens: int = 1000) -> str:
        """Async completion across all providers."""
        try:
            client = self._get_client()
            if self.provider == "openai":
                resp = await client.chat.completions.create(
                    model=self.model or settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content.strip()

            elif self.provider == "anthropic":
                resp = await client.messages.create(
                    model=self.model or settings.ANTHROPIC_MODEL,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                return resp.content[0].text.strip()

            elif self.provider == "gemini":
                import asyncio
                resp = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.generate_content(f"{system_prompt}\n\n{user_prompt}")
                )
                return resp.text.strip()

        except Exception as e:
            logger.error(f"AI completion failed ({self.provider}): {e}")
            return ""

    # ── Specialized analysis methods ────────────────────────────────────────

    async def analyze_anomaly(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Analyze a metric anomaly and provide root cause + recommendations."""
        system = """You are an expert SRE/DevOps AI assistant for Nexus Platform.
Analyze infrastructure anomalies and provide:
1. A brief summary (1-2 sentences)
2. Likely root cause
3. Recommended actions (prioritized list)
4. Confidence level (0.0-1.0)
Respond in JSON format: {"summary": "...", "root_cause": "...", "recommendation": "...", "confidence": 0.85}
Always respond in the same language as the context (pt-BR if Portuguese data is present)."""

        user = f"""Anomaly detected:
- Entity: {context.get('entity_type')} / {context.get('entity_name')} ({context.get('entity_id')})
- Metric: {context.get('metric_name')}
- Observed value: {context.get('observed_value')}
- Expected (mean ± std): {context.get('expected_mean')} ± {context.get('expected_std')}
- Deviation: {context.get('deviation_sigma'):.1f} sigma
- Timestamp: {context.get('timestamp')}
- Recent history: {context.get('recent_history', [])}
- Related metrics: {context.get('related_metrics', {})}
- Current alerts: {context.get('current_alerts', [])}"""

        import json
        result_text = await self.complete(system, user, temperature=0.2, max_tokens=600)
        try:
            return json.loads(result_text)
        except Exception:
            return {"summary": result_text, "root_cause": "", "recommendation": "", "confidence": 0.5}

    async def analyze_security_event(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Analyze IDS alerts and security events for threat intelligence."""
        system = """You are a cybersecurity AI analyst for Nexus Platform.
Analyze security events and IDS alerts. Provide:
1. Summary of the threat
2. Threat level assessment (critical/high/medium/low/info)
3. MITRE ATT&CK TTPs if applicable
4. Indicators of Compromise (IOCs)
5. Recommended mitigations
6. Whether this is likely a false positive
Respond in JSON format:
{"summary":"...","threat_level":"high","ttps":["T1110"],"ioc":["1.2.3.4"],"recommendation":"...","is_false_positive":false}"""

        user = f"""Security Event:
- Type: {context.get('event_type')} / {context.get('attack_type')}
- Severity: {context.get('severity')}
- Source IP: {context.get('source_ip')} ({context.get('source_country', 'unknown')})
- Target: {context.get('dest_ip')}:{context.get('dest_port')} ({context.get('protocol')})
- Attempts: {context.get('attempts', 1)}
- Rule: {context.get('rule_name')}
- Raw log: {context.get('raw_log', '')[:500]}
- Host context: {context.get('host_info', {})}
- Recent similar events: {context.get('similar_events_count', 0)} in last 1h"""

        import json
        result_text = await self.complete(system, user, temperature=0.1, max_tokens=800)
        try:
            return json.loads(result_text)
        except Exception:
            return {"summary": result_text, "threat_level": "medium", "ttps": [],
                    "ioc": [], "recommendation": "", "is_false_positive": False}

    async def analyze_trace(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Analyze OTel traces to explain errors and suggest fixes."""
        system = """You are an expert distributed systems / APM AI for Nexus Platform.
Analyze application traces and explain:
1. What happened (plain language summary)
2. Root cause of the error/latency
3. Which service/component caused it
4. Consequence (business/user impact)
5. One or more solutions with priority
Respond in JSON:
{"summary":"...","root_cause":"...","impact":"...","solutions":[{"priority":1,"action":"...","effort":"low/medium/high"}],"confidence":0.9}"""

        user = f"""Trace Analysis Request:
- Trace ID: {context.get('trace_id')}
- Service: {context.get('service')}
- Endpoint: {context.get('method')} {context.get('url')}
- Status: {context.get('status')} / HTTP {context.get('response_code')}
- Duration: {context.get('duration_ms')}ms
- Error count: {context.get('error_count')} spans
- Span tree: {context.get('spans', [])}
- Attributes: {context.get('attributes', {})}
- Events (errors/exceptions): {context.get('events', [])}"""

        import json
        result_text = await self.complete(system, user, temperature=0.2, max_tokens=800)
        try:
            return json.loads(result_text)
        except Exception:
            return {"summary": result_text, "root_cause": "", "impact": "",
                    "solutions": [], "confidence": 0.5}

    async def analyze_log_security(self, logs: List[Dict], context: Dict) -> Dict[str, Any]:
        """Analyze a batch of logs for security anomalies and intrusion attempts."""
        system = """You are a Security Operations Center (SOC) AI analyst.
Analyze log batches for:
- Intrusion attempts (brute force, privilege escalation, lateral movement)
- Anomalous patterns (unusual hours, impossible travel, unusual volume)
- Known attack signatures
- Data exfiltration indicators
Respond in JSON:
{"anomalies":[{"type":"brute_force","severity":"high","description":"...","affected_ips":[],"recommendation":"..."}],"overall_risk":"medium","summary":"..."}"""

        import json
        log_text = json.dumps(logs[:50], indent=2)  # limit to 50 logs per batch
        user = f"""Log batch for security analysis:
Context: {json.dumps(context)}
Logs ({len(logs)} total, showing first 50):
{log_text}"""

        result_text = await self.complete(system, user, temperature=0.1, max_tokens=1200)
        try:
            return json.loads(result_text)
        except Exception:
            return {"anomalies": [], "overall_risk": "low", "summary": result_text}

    async def generate_baseline_description(self, baseline: Dict) -> str:
        """Generate human-readable description of a metric baseline."""
        system = "You are a monitoring expert. Describe metric baselines in 1-2 sentences for ops teams."
        user = f"""Describe this baseline:
- Metric: {baseline.get('metric_name')} on {baseline.get('entity_type')} {baseline.get('entity_id')}
- Mean: {baseline.get('mean'):.2f}, Std: {baseline.get('std_dev'):.2f}
- P95: {baseline.get('p95'):.2f}, Max: {baseline.get('max_val'):.2f}
- Warning threshold: {baseline.get('warn_threshold'):.2f}
- Critical threshold: {baseline.get('crit_threshold'):.2f}
- Sample count: {baseline.get('sample_count')}"""
        return await self.complete(system, user, temperature=0.4, max_tokens=150)


# Singleton
ai_engine = AIEngine()
