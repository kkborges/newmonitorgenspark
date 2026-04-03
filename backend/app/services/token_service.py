"""
Token Service — Auto-generates tokens for agents, gateways, OTel and APM.
Called when user clicks "Download" installer — no manual token needed.
"""
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AgentToken, Gateway, Tenant
from app.core.config import settings


def _generate_token(prefix: str, length: int = 48) -> str:
    """Generate a secure token with prefix: nxa_<random> or nxg_<random>"""
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}_{random_part}"


async def create_agent_token(
    db: AsyncSession,
    tenant_id: str,
    role: str = "agent",
    name: Optional[str] = None,
    description: Optional[str] = None,
    expires_days: Optional[int] = None,
    install_config: Optional[dict] = None,
) -> AgentToken:
    """
    Auto-create and persist an agent token.
    Called on-demand when downloading an installer script.
    """
    token_str = _generate_token(settings.AGENT_TOKEN_PREFIX)

    expires_at = None
    if expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    token = AgentToken(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        token=token_str,
        name=name or f"Agent Token {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        description=description or f"Auto-generated on download ({role})",
        role=role,
        active=True,
        expires_at=expires_at,
        install_config=install_config or {},
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token


async def create_gateway_token(
    db: AsyncSession,
    tenant_id: str,
    name: str,
    gateway_type: str = "infra",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> Gateway:
    """
    Auto-create a gateway with a fresh token.
    """
    token_str = _generate_token(settings.GATEWAY_TOKEN_PREFIX)

    gateway = Gateway(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        type=gateway_type,
        host=host,
        port=port,
        token=token_str,
        status="offline",
    )
    db.add(gateway)
    await db.commit()
    await db.refresh(gateway)
    return gateway


async def get_or_create_otel_token(
    db: AsyncSession,
    tenant_id: str,
    service_name: Optional[str] = None,
) -> AgentToken:
    """
    Get existing OTel token for tenant or create one automatically.
    """
    from sqlalchemy import select

    existing = await db.execute(
        select(AgentToken).where(
            AgentToken.tenant_id == tenant_id,
            AgentToken.role == "otel",
            AgentToken.active == True,
        )
    )
    token = existing.scalar_one_or_none()

    if not token:
        token = await create_agent_token(
            db=db,
            tenant_id=tenant_id,
            role="otel",
            name=f"OTel Token — {service_name or 'default'}",
            description="Auto-generated OTel/APM token",
        )

    return token


def build_linux_install_script(
    platform_url: str,
    token: str,
    role: str = "agent",
    modules: list = None,
) -> str:
    """Generate the Linux bash installer with embedded token."""
    modules_str = ",".join(modules or ["infra", "logs", "otel"])
    return f"""#!/bin/bash
# ============================================================
# Nexus Platform Agent Installer v4.0
# Auto-generated — token embedded, no manual configuration needed
# ============================================================

set -e

NEXUS_URL="{platform_url}"
NEXUS_TOKEN="{token}"
NEXUS_ROLE="{role}"
NEXUS_MODULES="{modules_str}"
NEXUS_VERSION="4.0.0"
INSTALL_DIR="/opt/nexus"
SERVICE_NAME="nexus-agent"
LOG_DIR="/var/log/nexus"
CONFIG_DIR="/etc/nexus"

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

echo -e "${{BLUE}}"
echo "  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗"
echo "  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝"
echo "  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗"
echo "  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║"
echo "  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║"
echo "  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo -e "${{NC}}"
echo -e "${{GREEN}}Nexus Platform v4.0 — Instalação do Agente${{NC}}"
echo ""

# Check root
if [[ $EUID -ne 0 ]]; then
   echo -e "${{RED}}ERRO: Execute como root (sudo bash install.sh)${{NC}}"
   exit 1
fi

detect_os() {{
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        echo -e "${{RED}}Sistema operacional não suportado${{NC}}"
        exit 1
    fi
    echo -e "Sistema detectado: ${{GREEN}}$OS $OS_VERSION${{NC}}"
}}

install_dependencies() {{
    echo -e "${{YELLOW}}Instalando dependências...${{NC}}"
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip curl wget ca-certificates systemd net-tools
            ;;
        centos|rhel|fedora|rocky|almalinux)
            yum install -y python3 python3-pip curl wget ca-certificates net-tools 2>/dev/null || \
            dnf install -y python3 python3-pip curl wget ca-certificates net-tools
            ;;
        alpine)
            apk add --no-cache python3 py3-pip curl wget ca-certificates
            ;;
    esac
}}

create_directories() {{
    mkdir -p $INSTALL_DIR $LOG_DIR $CONFIG_DIR
    chmod 750 $CONFIG_DIR $INSTALL_DIR
    chmod 755 $LOG_DIR
}}

write_config() {{
    cat > $CONFIG_DIR/nexus.conf << 'CONF'
[nexus]
nexus_url = {platform_url}
agent_token = {token}
role = {role}
modules = {modules_str}
log_dir = /var/log/nexus
install_dir = /opt/nexus

[intervals]
heartbeat_interval = 60
metrics_interval = 30
log_batch_interval = 30
ids_scan_interval = 60

[features]
process_monitor = true
port_scan = true
disk_monitor = true
network_monitor = true
log_collection = true
otel_enabled = false
ids_enabled = false
apm_enabled = false

[log_paths]
paths = /var/log/syslog,/var/log/auth.log,/var/log/nginx/*.log,/var/log/apache2/*.log

[security]
tls_verify = true
compress_data = true
encrypt_data = true
CONF
    chmod 600 $CONFIG_DIR/nexus.conf
}}

download_agent() {{
    echo -e "${{YELLOW}}Baixando agente...${{NC}}"
    curl -fsSL "$NEXUS_URL/api/agent/download/linux" \
        -H "Authorization: Bearer $NEXUS_TOKEN" \
        -o $INSTALL_DIR/nexus-agent.py
    chmod +x $INSTALL_DIR/nexus-agent.py
}}

install_pip_deps() {{
    echo -e "${{YELLOW}}Instalando dependências Python...${{NC}}"
    pip3 install -q psutil requests cryptography 2>/dev/null || true
}}

install_service() {{
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Nexus Platform Agent v4.0
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=10
User=root
ExecStart=/usr/bin/python3 $INSTALL_DIR/nexus-agent.py
StandardOutput=append:$LOG_DIR/agent.log
StandardError=append:$LOG_DIR/agent-error.log
Environment=NEXUS_CONFIG=$CONFIG_DIR/nexus.conf

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    systemctl start $SERVICE_NAME
    sleep 2
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${{GREEN}}✅ Agente instalado e rodando!${{NC}}"
    else
        echo -e "${{RED}}❌ Falha ao iniciar o agente. Verifique os logs: journalctl -u $SERVICE_NAME${{NC}}"
        exit 1
    fi
}}

verify_connection() {{
    echo -e "${{YELLOW}}Verificando conexão com a plataforma...${{NC}}"
    RESPONSE=$(curl -s -o /dev/null -w "%{{http_code}}" \
        "$NEXUS_URL/api/agent/ping" \
        -H "Authorization: Bearer $NEXUS_TOKEN")
    
    if [ "$RESPONSE" = "200" ]; then
        echo -e "${{GREEN}}✅ Conexão com a plataforma estabelecida!${{NC}}"
    else
        echo -e "${{YELLOW}}⚠️  Não foi possível verificar conexão (HTTP $RESPONSE). O agente tentará novamente.${{NC}}"
    fi
}}

# Main installation
detect_os
install_dependencies
create_directories
write_config
install_pip_deps
download_agent
install_service
verify_connection

echo ""
echo -e "${{GREEN}}============================================${{NC}}"
echo -e "${{GREEN}}✅ Nexus Agent instalado com sucesso!${{NC}}"
echo -e "${{GREEN}}============================================${{NC}}"
echo ""
echo "  Token: ${{YELLOW}}{token}${{NC}}"
echo "  Plataforma: ${{BLUE}}{platform_url}${{NC}}"
echo "  Logs: ${{BLUE}}journalctl -u $SERVICE_NAME -f${{NC}}"
echo ""
"""


def build_windows_install_script(platform_url: str, token: str, role: str = "agent") -> str:
    """Generate the Windows PowerShell installer with embedded token."""
    return f"""# ============================================================
# Nexus Platform Agent Installer v4.0 - Windows PowerShell
# Auto-generated — token embedded
# ============================================================

$ErrorActionPreference = "Stop"

$NEXUS_URL = "{platform_url}"
$NEXUS_TOKEN = "{token}"
$NEXUS_ROLE = "{role}"
$NEXUS_VERSION = "4.0.0"
$INSTALL_DIR = "C:\\NexusAgent"
$CONFIG_DIR = "C:\\NexusAgent\\config"
$LOG_DIR = "C:\\NexusAgent\\logs"
$SERVICE_NAME = "NexusAgent"

Write-Host ""
Write-Host "  ██╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗" -ForegroundColor Cyan
Write-Host "  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝" -ForegroundColor Cyan
Write-Host "  Nexus Platform v4.0 - Windows Agent Install" -ForegroundColor Green
Write-Host ""

# Check Admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {{
    Write-Host "ERRO: Execute como Administrador!" -ForegroundColor Red
    exit 1
}}

# Create directories
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null

# Write config
@"
[nexus]
nexus_url = {platform_url}
agent_token = {token}
role = {role}
log_dir = C:\\NexusAgent\\logs
install_dir = C:\\NexusAgent

[intervals]
heartbeat_interval = 60
metrics_interval = 30
ids_scan_interval = 60

[features]
process_monitor = true
port_scan = true
disk_monitor = true
network_monitor = true
log_collection = true
ids_enabled = true

[ids]
event_log_sources = Security,System,Application
"@ | Set-Content "$CONFIG_DIR\\nexus.conf" -Encoding UTF8

# Download Python agent
Write-Host "Baixando agente Python..." -ForegroundColor Yellow
$headers = @{{ "Authorization" = "Bearer $NEXUS_TOKEN" }}
Invoke-WebRequest -Uri "$NEXUS_URL/api/agent/download/windows" `
    -Headers $headers `
    -OutFile "$INSTALL_DIR\\nexus-agent.py"

# Check Python
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $pythonPath) {{
    Write-Host "Python não encontrado. Instalando Python 3.12..." -ForegroundColor Yellow
    $pythonInstaller = "$env:TEMP\\python-installer.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe" -OutFile $pythonInstaller
    Start-Process -Wait -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1"
    $pythonPath = "C:\\Python312\\python.exe"
}}

# Install dependencies
& pip install psutil requests cryptography pywin32 wmi -q

# Install as Windows Service using NSSM
$nssmPath = "$INSTALL_DIR\\nssm.exe"
if (-not (Test-Path $nssmPath)) {{
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\\nssm.zip"
    Expand-Archive -Path "$env:TEMP\\nssm.zip" -DestinationPath "$env:TEMP\\nssm"
    Copy-Item "$env:TEMP\\nssm\\nssm-2.24\\win64\\nssm.exe" $nssmPath
}}

& $nssmPath install $SERVICE_NAME $pythonPath "$INSTALL_DIR\\nexus-agent.py"
& $nssmPath set $SERVICE_NAME AppParameters "$INSTALL_DIR\\nexus-agent.py"
& $nssmPath set $SERVICE_NAME AppDirectory $INSTALL_DIR
& $nssmPath set $SERVICE_NAME AppStdout "$LOG_DIR\\agent.log"
& $nssmPath set $SERVICE_NAME AppStderr "$LOG_DIR\\agent-error.log"
& $nssmPath set $SERVICE_NAME Start SERVICE_AUTO_START
& $nssmPath set $SERVICE_NAME AppEnvironmentExtra "NEXUS_CONFIG=$CONFIG_DIR\\nexus.conf"

Start-Service $SERVICE_NAME

$status = (Get-Service -Name $SERVICE_NAME).Status
if ($status -eq "Running") {{
    Write-Host ""
    Write-Host "✅ Nexus Agent instalado e rodando!" -ForegroundColor Green
    Write-Host "   Token: {token}" -ForegroundColor Yellow
    Write-Host "   Plataforma: {platform_url}" -ForegroundColor Cyan
    Write-Host "   Logs: $LOG_DIR\\agent.log" -ForegroundColor Cyan
}} else {{
    Write-Host "❌ Falha ao iniciar serviço. Verifique os logs." -ForegroundColor Red
    exit 1
}}
"""


def build_docker_compose(platform_url: str, token: str) -> str:
    return f"""version: '3.8'
services:
  nexus-agent:
    image: nexusplatform/agent:4.0
    container_name: nexus-agent
    restart: unless-stopped
    environment:
      NEXUS_URL: "{platform_url}"
      NEXUS_TOKEN: "{token}"
      NEXUS_ROLE: "agent"
      NEXUS_MODULES: "infra,logs,otel"
    volumes:
      - /var/log:/host/var/log:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /etc:/host/etc:ro
    network_mode: host
    privileged: true
    labels:
      - "com.nexus.managed=true"
"""


def build_k8s_manifest(platform_url: str, token: str) -> str:
    return f"""apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nexus-agent
  namespace: nexus-monitoring
  labels:
    app: nexus-agent
spec:
  selector:
    matchLabels:
      app: nexus-agent
  template:
    metadata:
      labels:
        app: nexus-agent
    spec:
      hostNetwork: true
      hostPID: true
      tolerations:
        - key: node-role.kubernetes.io/master
          effect: NoSchedule
        - key: node-role.kubernetes.io/control-plane
          effect: NoSchedule
      containers:
        - name: nexus-agent
          image: nexusplatform/agent:4.0
          env:
            - name: NEXUS_URL
              value: "{platform_url}"
            - name: NEXUS_TOKEN
              value: "{token}"
            - name: NEXUS_ROLE
              value: "k8s"
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          volumeMounts:
            - name: proc
              mountPath: /host/proc
              readOnly: true
            - name: sys
              mountPath: /host/sys
              readOnly: true
            - name: varlog
              mountPath: /var/log
              readOnly: true
          securityContext:
            privileged: true
      volumes:
        - name: proc
          hostPath:
            path: /proc
        - name: sys
          hostPath:
            path: /sys
        - name: varlog
          hostPath:
            path: /var/log
---
apiVersion: v1
kind: Namespace
metadata:
  name: nexus-monitoring
"""
