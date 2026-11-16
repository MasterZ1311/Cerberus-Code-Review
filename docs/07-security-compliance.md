# Cerberus - Security & Compliance Guide

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## Table of Contents

- [Security Architecture](#security-architecture)
- [Data Privacy](#data-privacy)
- [LLM Provider Security](#llm-provider-security)
- [Secure Deployment](#secure-deployment)
- [Audit & Compliance](#audit--compliance)
- [Incident Response](#incident-response)
- [Security Checklist](#security-checklist)

---

## Security Architecture

### Authentication & Authorization

**API Key Management:**

```yaml
# Strong API key generation
security:
  api_keys:
    format: "cvai_{32_random_chars}"
    algorithm: "secrets.token_urlsafe"
    min_length: 32
    
  # Key rotation
  key_rotation:
    max_age_days: 90
    warn_before_expiry_days: 14
```

**Role-Based Access Control (RBAC):**

```python
# API key scopes
scopes = [
    "review:read",      # Read review results
    "review:write",     # Submit reviews
    "config:read",      # Read configuration
    "config:write",     # Modify configuration
    "admin:*"           # Full admin access
]

# Creating scoped keys
cerberus-cli create-api-key \
  --name "ci-cd-key" \
  --scopes "review:read,review:write"
```

### Network Security

**TLS/HTTPS Configuration:**

```nginx
# nginx.conf
server {
    listen 443 ssl http2;
    server_name api.cerberus.example.com;
    
    # SSL certificates
    ssl_certificate /etc/ssl/certs/cerberus.crt;
    ssl_certificate_key /etc/ssl/private/cerberus.key;
    
    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass http://cerberus-api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Firewall Rules:**

```bash
# Allow only necessary ports
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 443/tcp   # HTTPS
ufw enable

# Docker-specific rules
iptables -A INPUT -i docker0 -j ACCEPT
iptables -A INPUT -p tcp --dport 5432 -s 172.17.0.0/16 -j ACCEPT  # PostgreSQL (internal only)
iptables -A INPUT -p tcp --dport 6379 -s 172.17.0.0/16 -j ACCEPT  # Redis (internal only)
```

### Secrets Management

**Using Docker Secrets:**

```yaml
# docker-compose.yml
services:
  api:
    secrets:
      - openai_api_key
      - database_password
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
      - DATABASE_PASSWORD_FILE=/run/secrets/database_password

secrets:
  openai_api_key:
    file: ./secrets/openai_api_key.txt
  database_password:
    file: ./secrets/database_password.txt
```

**Using HashiCorp Vault:**

```python
# vault_config.py
import hvac

client = hvac.Client(url='https://vault.example.com')
client.auth.approle.login(
    role_id=os.getenv('VAULT_ROLE_ID'),
    secret_id=os.getenv('VAULT_SECRET_ID')
)

# Read secrets
openai_key = client.secrets.kv.v2.read_secret_version(
    path='cerberus/openai'
)['data']['data']['api_key']
```

**Using AWS Secrets Manager:**

```python
import boto3

secrets = boto3.client('secretsmanager', region_name='us-east-1')
response = secrets.get_secret_value(SecretId='cerberus/openai-key')
openai_key = response['SecretString']
```

---

## Data Privacy

### Data Collection & Retention

**What Data is Collected:**

| Data Type | Stored | Retention | Purpose |
|-----------|--------|-----------|---------|
| Code content | Optional | Configurable | Review analysis |
| Review results | Yes | 90 days default | Audit trail |
| API keys (hashed) | Yes | Until revoked | Authentication |
| User metadata | Minimal | Indefinite | Account management |
| Logs | Yes | 30 days | Troubleshooting |
| Metrics | Aggregated | 1 year | Performance monitoring |

**Data Retention Configuration:**

```yaml
privacy:
  # Code retention
  code_retention:
    enabled: false              # Don't store code by default
    ttl_days: 7                 # If enabled, delete after 7 days
    
  # Review results retention
  review_retention:
    enabled: true
    ttl_days: 90                # Keep results for 90 days
    
  # Log retention
  log_retention:
    ttl_days: 30
    
  # PII handling
  pii:
    redact_in_logs: true
    anonymize_in_metrics: true
```

### Data Encryption

**At Rest:**

```yaml
# PostgreSQL encryption
database:
  encryption:
    enabled: true
    method: "pgcrypto"
    key_file: "/secrets/db-encryption-key"

# Redis encryption
cache:
  encryption:
    enabled: true
    method: "AES-256-GCM"
```

**In Transit:**

```yaml
# Force TLS for all connections
security:
  tls:
    required: true
    min_version: "1.2"
    
  # Database connections
  database:
    ssl_mode: "require"
    ssl_cert: "/certs/client-cert.pem"
    ssl_key: "/certs/client-key.pem"
```

### GDPR/CCPA Compliance

**Data Subject Rights:**

```bash
# Right to access
cerberus-cli user export --user-id user_123 --format json

# Right to deletion
cerberus-cli user delete --user-id user_123 --confirm

# Right to portability
cerberus-cli user export --user-id user_123 --format csv
```

**Consent Management:**

```yaml
privacy:
  consent:
    required: true
    purposes:
      - "code_analysis"
      - "performance_improvement"
      - "security_monitoring"
```

**Data Processing Agreement (DPA):**

- Available at: docs/legal/dpa.md
- Review with legal counsel before deployment
- Update based on jurisdiction

---

## LLM Provider Security

### Data Sharing with Providers

**OpenAI:**
- **Data Retention**: 30 days (as of 2024)
- **Zero Retention**: Available for enterprise
- **Data Usage**: Not used for training (API usage)
- **Privacy Policy**: https://openai.com/privacy

**Anthropic:**
- **Data Retention**: Not used for training
- **Privacy Policy**: https://anthropic.com/privacy

**Ollama (Local):**
- **Data Retention**: All local, never leaves infrastructure
- **Privacy**: Complete control

### Privacy Comparison

| Provider | Data Sent | Retention | Training | Best For |
|----------|-----------|-----------|----------|----------|
| OpenAI | Code snippets | 30 days | No (API) | General use |
| OpenAI (Zero-retention) | Code snippets | 0 days | No | Sensitive code |
| Anthropic | Code snippets | Not used | No | General use |
| Ollama | None (local) | Local only | N/A | Maximum privacy |
| Azure OpenAI | Code snippets | Customer-controlled | No | Enterprise |

### Using Local Models for Sensitive Code

**Configuration:**

```yaml
# Route sensitive projects to local Ollama
llm:
  routing:
    - pattern: "*/sensitive-project/*"
      provider: "ollama"
    - pattern: "*/financial-services/*"
      provider: "ollama"
    - default: "openai"
```

**Encryption for Cloud Providers:**

```python
# Encrypt code before sending to LLM (advanced)
from cryptography.fernet import Fernet

def encrypt_code(code: str, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(code.encode()).decode()

# Note: This impacts LLM understanding - use with caution
```

---

## Secure Deployment

### Docker Security Hardening

**Run as Non-Root User:**

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 cerberus && \
    chown -R cerberus:cerberus /app

USER cerberus

# Rest of Dockerfile...
```

**Container Security:**

```yaml
# docker-compose.yml
services:
  api:
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
```

**Resource Limits:**

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Kubernetes Security

**Pod Security Policy:**

```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: cerberus-psp
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
    - ALL
  volumes:
    - 'configMap'
    - 'emptyDir'
    - 'projected'
    - 'secret'
  hostNetwork: false
  hostIPC: false
  hostPID: false
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
```

**Network Policies:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: cerberus-api-policy
spec:
  podSelector:
    matchLabels:
      app: cerberus-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nginx-ingress
      ports:
        - protocol: TCP
          port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
```

### Dependency Scanning

**Automated Scanning:**

```yaml
# .github/workflows/security-scan.yml
name: Security Scan

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Run Snyk security scan
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
```

**Regular Updates:**

```bash
# Update dependencies weekly
pip install --upgrade pip
pip install --upgrade -r requirements.txt

# Scan for vulnerabilities
pip-audit

# Update Docker base images
docker pull python:3.11-slim
docker build -t cerberus/api:latest .
```

---

## Audit & Compliance

### Audit Logging

**Enabled by Default:**

```yaml
audit:
  enabled: true
  log_all_api_calls: true
  log_file: "/var/log/cerberus/audit.log"
  
  # What to log
  events:
    - api_key_created
    - api_key_revoked
    - review_submitted
    - config_changed
    - user_login
    - user_logout
```

**Audit Log Format:**

```json
{
  "timestamp": "2026-09-21T10:30:00Z",
  "event_type": "review_submitted",
  "user_id": "user_123",
  "api_key_id": "key_abc",
  "ip_address": "192.168.1.100",
  "user_agent": "cerberus-cli/0.1.0",
  "resource": "review",
  "resource_id": "rev_xyz789",
  "action": "create",
  "result": "success",
  "metadata": {
    "language": "python",
    "file_count": 1,
    "agents": ["security", "quality"]
  }
}
```

### Review History & Traceability

**Immutable Audit Trail:**

```sql
-- Audit table (append-only)
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    user_id VARCHAR(50),
    resource_type VARCHAR(50),
    resource_id VARCHAR(50),
    action VARCHAR(20),
    result VARCHAR(20),
    metadata JSONB,
    
    -- Prevent updates/deletes
    CONSTRAINT audit_log_immutable CHECK (false)
);

-- Only INSERT allowed
GRANT INSERT ON audit_log TO cerberus_app;
REVOKE UPDATE, DELETE ON audit_log FROM cerberus_app;
```

### SOC 2 / ISO 27001 Considerations

**Access Controls:**
- ✅ Role-based access control (RBAC)
- ✅ Multi-factor authentication (MFA) for admin access
- ✅ Least privilege principle
- ✅ Regular access reviews

**Data Protection:**
- ✅ Encryption at rest and in transit
- ✅ Data retention policies
- ✅ Secure key management
- ✅ Regular backups

**Monitoring & Logging:**
- ✅ Comprehensive audit logging
- ✅ Security event monitoring
- ✅ Log retention (1 year minimum)
- ✅ Intrusion detection

**Incident Response:**
- ✅ Documented incident response plan
- ✅ Security incident logging
- ✅ Breach notification procedures
- ✅ Regular security testing

### Evidence Collection

**Automated Evidence Collection:**

```bash
#!/bin/bash
# collect-compliance-evidence.sh

DATE=$(date +%Y%m%d)
OUTPUT_DIR="/compliance/evidence/$DATE"

mkdir -p "$OUTPUT_DIR"

# Access logs
cp /var/log/cerberus/audit.log "$OUTPUT_DIR/"

# Configuration snapshot
cp -r /etc/cerberus/ "$OUTPUT_DIR/config/"

# User access report
cerberus-cli users list --format csv > "$OUTPUT_DIR/users.csv"

# API key audit
cerberus-cli api-keys audit --format csv > "$OUTPUT_DIR/api-keys.csv"

# Security scan results
trivy fs --format json . > "$OUTPUT_DIR/vulnerability-scan.json"

# Package evidence
tar -czf "/compliance/evidence-$DATE.tar.gz" "$OUTPUT_DIR"
```

---

## Incident Response

### Security Incident Procedures

**Phase 1: Detection & Analysis**

1. Alert received (monitoring, user report, etc.)
2. Verify incident is genuine (not false positive)
3. Assess severity: Critical / High / Medium / Low
4. Document initial findings

**Phase 2: Containment**

```bash
# Immediate actions for security breach:

# 1. Revoke compromised API keys
cerberus-cli api-key revoke --key-id key_compromised

# 2. Block suspicious IPs
ufw deny from 1.2.3.4

# 3. Enable stricter rate limiting
cerberus-cli config set rate_limit_per_hour 10

# 4. Rotate secrets if needed
cerberus-cli secrets rotate --all --force
```

**Phase 3: Eradication**

- Identify and fix root cause
- Apply security patches
- Remove malicious access
- Clean compromised systems

**Phase 4: Recovery**

```bash
# Restore from backup if needed
./restore-from-backup.sh

# Restart services
docker-compose restart

# Verify integrity
./verify-system-integrity.sh
```

**Phase 5: Post-Incident**

- Document lessons learned
- Update security procedures
- Implement preventive measures
- Notify affected users (if applicable)

### Breach Notification

**When Required:**
- Personal data exposed
- Unauthorized access to systems
- Data integrity compromised

**Notification Template:**

```
Subject: Security Incident Notification - Cerberus

Dear [User/Customer],

We are writing to inform you of a security incident that may have affected your data.

Incident Summary:
- Date Detected: [DATE]
- Nature of Incident: [DESCRIPTION]
- Data Affected: [TYPES OF DATA]
- Number of Users Affected: [NUMBER]

Actions Taken:
- [ACTION 1]
- [ACTION 2]

Actions Required by You:
- [ACTION 1]
- [ACTION 2]

We apologize for this incident and are committed to preventing future occurrences.

For questions: security@cerberus.ai
```

### Recovery Procedures

**Database Recovery:**

```bash
# Stop services
docker-compose stop api

# Restore from backup
docker-compose exec db psql -U cerberus < /backups/cerberus-latest.sql

# Verify integrity
docker-compose exec db psql -U cerberus -c "SELECT COUNT(*) FROM reviews;"

# Restart services
docker-compose start api
```

**Configuration Recovery:**

```bash
# Restore configuration from version control
git checkout main -- config/

# Verify configuration
cerberus-cli config validate

# Restart services
docker-compose restart
```

---

## Security Checklist

### Pre-Deployment Checklist

- [ ] Change all default passwords
- [ ] Enable TLS/HTTPS with valid certificates
- [ ] Configure firewall rules
- [ ] Set up secrets management (Vault/Secrets Manager)
- [ ] Enable audit logging
- [ ] Configure data retention policies
- [ ] Set up automated backups
- [ ] Enable monitoring and alerting
- [ ] Review and minimize attack surface
- [ ] Scan for vulnerabilities (Trivy, Snyk)
- [ ] Test incident response procedures
- [ ] Document security architecture
- [ ] Configure rate limiting
- [ ] Enable MFA for admin access
- [ ] Review LLM provider privacy policies
- [ ] Set up network isolation
- [ ] Configure resource limits
- [ ] Enable security headers
- [ ] Test disaster recovery
- [ ] Review API key scopes
- [ ] Set up log aggregation

### Ongoing Security Tasks

**Daily:**
- [ ] Review security alerts
- [ ] Monitor error rates
- [ ] Check for unauthorized access attempts

**Weekly:**
- [ ] Review audit logs
- [ ] Check for dependency updates
- [ ] Verify backup integrity

**Monthly:**
- [ ] Update dependencies and patch systems
- [ ] Review and rotate API keys (if needed)
- [ ] Conduct vulnerability scans
- [ ] Review access permissions
- [ ] Test backup restoration

**Quarterly:**
- [ ] Security audit
- [ ] Penetration testing
- [ ] Review and update security policies
- [ ] Conduct tabletop incident response exercises
- [ ] Review compliance requirements

**Annually:**
- [ ] Comprehensive security review
- [ ] Update disaster recovery plan
- [ ] Review and update incident response plan
- [ ] Security training for team
- [ ] Third-party security assessment

---

**Next Steps:**
- [Developer Guide](08-developer-guide.md) - Extend functionality
- [Installation Guide](04-installation-setup.md) - Deploy securely

---

*Cerberus Security & Compliance Guide - v0.1.0*
