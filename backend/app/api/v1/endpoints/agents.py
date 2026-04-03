"""
Agent API — Download installers with auto-generated tokens.
GET /api/v1/agents/download/linux?role=agent&modules=infra,logs,otel
GET /api/v1/agents/download/windows
GET /api/v1/agents/download/docker
GET /api/v1/agents/download/k8s
POST /api/v1/agents/tokens  — create token manually
GET  /api/v1/agents/tokens  — list tokens
DELETE /api/v1/agents/tokens/{id}
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.db.base import get_db
from app.middleware.auth import get_current_user
from app.services.token_service import (
    create_agent_token, build_linux_install_script,
    build_windows_install_script, build_docker_compose, build_k8s_manifest
)
from app.core.config import settings
from app.models import AgentToken
from sqlalchemy import select
import uuid

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/download/linux", response_class=PlainTextResponse)
async def download_linux_installer(
    role: str = Query("agent"),
    modules: Optional[str] = Query("infra,logs,otel"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Auto-generates a token and returns the Linux bash installer.
    No manual token creation needed!
    """
    token = await create_agent_token(
        db=db,
        tenant_id=user.tenant_id,
        role=role,
        name=f"Linux Agent ({role})",
        description=f"Auto-generated on download by {user.username}",
        install_config={"os": "linux", "modules": modules.split(",") if modules else []},
    )

    script = build_linux_install_script(
        platform_url=settings.PLATFORM_URL,
        token=token.token,
        role=role,
        modules=modules.split(",") if modules else None,
    )

    return PlainTextResponse(
        content=script,
        headers={
            "Content-Disposition": "attachment; filename=install-nexus-agent-linux.sh",
            "X-Token-ID": token.id,
        }
    )


@router.get("/download/windows", response_class=PlainTextResponse)
async def download_windows_installer(
    role: str = Query("agent"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    token = await create_agent_token(
        db=db,
        tenant_id=user.tenant_id,
        role=role,
        name=f"Windows Agent ({role})",
        description=f"Auto-generated on download by {user.username}",
        install_config={"os": "windows"},
    )

    script = build_windows_install_script(
        platform_url=settings.PLATFORM_URL,
        token=token.token,
        role=role,
    )

    return PlainTextResponse(
        content=script,
        headers={
            "Content-Disposition": "attachment; filename=install-nexus-agent.ps1",
            "X-Token-ID": token.id,
        }
    )


@router.get("/download/docker", response_class=PlainTextResponse)
async def download_docker_compose(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    token = await create_agent_token(
        db=db,
        tenant_id=user.tenant_id,
        role="agent",
        name="Docker Agent",
        description=f"Auto-generated for Docker by {user.username}",
        install_config={"os": "docker"},
    )

    script = build_docker_compose(
        platform_url=settings.PLATFORM_URL,
        token=token.token,
    )

    return PlainTextResponse(
        content=script,
        headers={"Content-Disposition": "attachment; filename=docker-compose.nexus-agent.yml"}
    )


@router.get("/download/k8s", response_class=PlainTextResponse)
async def download_k8s_manifest(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    token = await create_agent_token(
        db=db,
        tenant_id=user.tenant_id,
        role="k8s",
        name="Kubernetes DaemonSet Agent",
        description=f"Auto-generated for K8s by {user.username}",
        install_config={"os": "kubernetes"},
    )

    manifest = build_k8s_manifest(
        platform_url=settings.PLATFORM_URL,
        token=token.token,
    )

    return PlainTextResponse(
        content=manifest,
        headers={"Content-Disposition": "attachment; filename=nexus-agent-daemonset.yaml"}
    )


@router.get("/download/otel-config", response_class=PlainTextResponse)
async def download_otel_config(
    service_name: Optional[str] = Query(None),
    language: str = Query("auto"),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Returns OpenTelemetry SDK configuration with auto-generated token.
    Supports: java, python, nodejs, dotnet, go, ruby.
    """
    from app.services.token_service import get_or_create_otel_token

    token = await get_or_create_otel_token(db, user.tenant_id, service_name)

    otel_endpoint = f"{settings.PLATFORM_URL}/api/v1/otel"

    configs = {
        "python": f"""# OTel SDK — Python (auto-configured)
# pip install opentelemetry-sdk opentelemetry-exporter-otlp

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

resource = Resource(attributes={{
    "service.name": "{service_name or 'my-service'}",
    "nexus.token": "{token.token}",
}})

provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(
    endpoint="{otel_endpoint}/traces",
    headers={{"Authorization": "Bearer {token.token}"}},
)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
""",
        "nodejs": f"""// OTel SDK — Node.js (auto-configured)
// npm install @opentelemetry/sdk-node @opentelemetry/exporter-trace-otlp-http

const {{ NodeSDK }} = require('@opentelemetry/sdk-node');
const {{ OTLPTraceExporter }} = require('@opentelemetry/exporter-trace-otlp-http');
const {{ Resource }} = require('@opentelemetry/resources');

const sdk = new NodeSDK({{
  resource: new Resource({{
    'service.name': '{service_name or 'my-service'}',
    'nexus.token': '{token.token}',
  }}),
  traceExporter: new OTLPTraceExporter({{
    url: '{otel_endpoint}/traces',
    headers: {{ Authorization: 'Bearer {token.token}' }},
  }}),
}});
sdk.start();
""",
        "java": f"""# OTel Agent — Java (auto-configured)
# Download: https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases

# Run your app with:
java -javaagent:opentelemetry-javaagent.jar \\
     -Dotel.service.name={service_name or 'my-service'} \\
     -Dotel.exporter.otlp.endpoint={otel_endpoint} \\
     -Dotel.exporter.otlp.headers="Authorization=Bearer {token.token}" \\
     -jar your-app.jar
""",
        "dotnet": f"""# OTel SDK — .NET (auto-configured)
# dotnet add package OpenTelemetry.Extensions.Hosting
# dotnet add package OpenTelemetry.Exporter.OpenTelemetryProtocol

builder.Services.AddOpenTelemetry()
    .WithTracing(tracer => tracer
        .SetResourceBuilder(ResourceBuilder.CreateDefault()
            .AddService("{service_name or 'my-service'}"))
        .AddOtlpExporter(opts => {{
            opts.Endpoint = new Uri("{otel_endpoint}/traces");
            opts.Headers = "Authorization=Bearer {token.token}";
        }}));
""",
        "go": f"""// OTel SDK — Go (auto-configured)
// go get go.opentelemetry.io/otel go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp

import (
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

exporter, _ := otlptracehttp.New(ctx,
    otlptracehttp.WithEndpoint("{settings.PLATFORM_URL.replace('http://', '').replace('https://', '')}"),
    otlptracehttp.WithURLPath("/api/v1/otel/traces"),
    otlptracehttp.WithHeaders(map[string]string{{
        "Authorization": "Bearer {token.token}",
    }}),
)
tp := sdktrace.NewTracerProvider(sdktrace.WithBatcher(exporter))
otel.SetTracerProvider(tp)
""",
    }

    if language == "auto":
        # Return all configs
        content = f"# OTel Token: {token.token}\n# Endpoint: {otel_endpoint}\n\n"
        content += "\n\n".join([f"## {lang.upper()}\n{code}" for lang, code in configs.items()])
    else:
        content = configs.get(language, configs["python"])

    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename=nexus-otel-{language}.txt"}
    )


@router.get("/tokens")
async def list_tokens(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    result = await db.execute(
        select(AgentToken).where(AgentToken.tenant_id == user.tenant_id)
        .order_by(AgentToken.created_at.desc())
    )
    tokens = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "role": t.role,
            "active": t.active,
            "token_preview": t.token[:12] + "...",
            "last_used": t.last_used,
            "created_at": t.created_at,
            "expires_at": t.expires_at,
        }
        for t in tokens
    ]


@router.delete("/tokens/{token_id}")
async def revoke_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    token = await db.get(AgentToken, token_id)
    if not token or token.tenant_id != user.tenant_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Token not found")
    token.active = False
    await db.commit()
    return {"status": "revoked"}
