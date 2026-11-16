# Changelog

All notable changes to Cerberus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-09-21

### 🎉 Initial Release

First public release of Cerberus!

### Added

#### Core Features
- Multi-agent code review system with three specialized agents:
  - Security Agent (v1.2.0) - Vulnerability detection
  - Performance Agent (v1.1.0) - Performance analysis
  - Code Quality Agent (v1.3.0) - Best practices review
- FastAPI-based REST API with complete OpenAPI documentation
- Intelligent caching system with Redis (70%+ hit rate)
- Git hooks integration (pre-commit and pre-push)
- CLI tool for on-demand reviews
- Batch review support for multiple files

#### LLM Provider Support
- OpenAI (GPT-4, GPT-4-turbo, GPT-3.5-turbo)
- Anthropic (Claude 3 Opus, Sonnet, Haiku)
- Ollama (local models: CodeLlama, Mistral, Llama2)
- Azure OpenAI
- Multi-provider fallback support

#### Deployment Options
- Docker Compose for local development
- Kubernetes manifests for cloud deployment
- AWS ECS/Fargate deployment guide
- GCP Cloud Run deployment guide
- Azure Container Apps deployment guide

#### Monitoring & Observability
- Prometheus metrics integration
- Grafana dashboards
- Structured JSON logging
- Health check endpoints
- Audit logging for compliance

#### Security Features
- API key authentication with RBAC
- TLS/HTTPS support
- Secrets management integration (Vault, AWS Secrets Manager)
- Data encryption at rest and in transit
- GDPR/CCPA compliance features
- Security incident response procedures

#### Documentation
- Complete documentation (100+ pages)
- Architecture overview with diagrams
- API reference with 5+ examples per endpoint
- Agent specifications with code examples
- Installation & setup guide
- Configuration reference
- Monitoring & operations guide
- Security & compliance guide
- Developer & contributing guide
- FAQ with 25+ questions
- Glossary of terms

#### Developer Experience
- Python SDK
- JavaScript/TypeScript SDK (examples)
- Custom agent development framework
- Extension API for custom integrations
- Webhook system for notifications
- SARIF export for tool integration

### Configuration

#### Default Settings
- Cache TTL: 7 days
- Review timeout: 30 seconds per agent
- Rate limit: 100 requests/hour per API key
- Default agents: Security, Performance, Quality
- Execution mode: Parallel

#### Environment Variables
- 30+ configuration environment variables
- Support for `.env` files
- Project-level `.cerberus.yml` config
- User-level configuration support

### Performance

- Review latency: <50ms (cached), 5-30s (uncached)
- Cache hit rate: 70%+ in typical usage
- Parallel agent execution for speed
- Efficient database connection pooling
- Redis-based result caching

### Known Limitations

- SQLite recommended for solo devs only (use PostgreSQL for teams)
- Maximum code size: 100KB per review
- No built-in team collaboration features (coming in 0.2.0)
- No historical trend analysis (planned for 0.3.0)
- IDE plugins are community-maintained

---

## [Unreleased]

### Planned for 0.2.0 (Q4 2026)

#### Features
- Team collaboration features
  - Shared review history
  - Team-wide configurations
  - Review assignment
  - Comments and discussions
- Advanced caching strategies
  - Multi-level cache
  - Distributed cache support
- Enhanced agent capabilities
  - Language-specific agents (Go, Rust, TypeScript)
  - Custom rule sets
  - AI-powered auto-fix suggestions
- Improved CI/CD integrations
  - GitHub App
  - GitLab integration
  - Bitbucket support

#### Improvements
- 30% faster review processing
- Better cache invalidation logic
- Improved LLM prompt engineering
- Enhanced error messages
- Reduced false positive rate

#### Bug Fixes
- Various performance optimizations
- Edge case handling improvements

---

## [Planned] Future Releases

### 0.3.0 - Historical Analysis & Trends (Q1 2027)
- Code quality trends over time
- Security posture tracking
- Technical debt visualization
- Team performance metrics
- Comparative analysis

### 0.4.0 - Advanced Features (Q2 2027)
- AI-powered auto-remediation
- Advanced custom agent marketplace
- Enhanced team features
- Real-time collaboration
- Advanced reporting

### 1.0.0 - Production Release (Q3 2027)
- Hosted SaaS version
- Enterprise features
- Advanced compliance reporting
- Priority support
- SLA guarantees

---

## Upgrade Guide

### Upgrading from Pre-release to 0.1.0

This is the first official release. If you were using pre-release versions:

1. **Backup your database**:
   ```bash
   docker-compose exec db pg_dump -U cerberus cerberus > backup.sql
   ```

2. **Pull latest images**:
   ```bash
   docker-compose pull
   ```

3. **Update configuration**:
   - Review new configuration options in `.env.example`
   - Update your `.env` file accordingly

4. **Run migrations**:
   ```bash
   docker-compose up -d
   docker-compose exec api python -m cerberus.cli migrate
   ```

5. **Verify installation**:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

---

## Release Schedule

- **Minor Releases** (0.x.0): Every 3 months
- **Patch Releases** (0.x.y): As needed for bug fixes
- **Security Patches**: Expedited release within 48 hours

---

## Deprecation Policy

- Deprecated features will be announced at least 6 months before removal
- API endpoints will maintain backward compatibility for at least 2 major versions
- Breaking changes only in major version releases (1.0, 2.0, etc.)

---

## Support

- **Latest Version**: Always supported
- **Previous Minor Version**: Supported for 6 months
- **Older Versions**: Community support only

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to contribute to Cerberus.

Report bugs and request features on [GitHub Issues](https://github.com/cerberus-ai/cerberus/issues).

---

## Links

- **Homepage**: https://cerberus.ai
- **Documentation**: https://docs.cerberus.ai
- **GitHub**: https://github.com/cerberus-ai/cerberus
- **Discord**: https://discord.gg/cerberus
- **Twitter**: https://twitter.com/cerberus

---

**[0.1.0]**: https://github.com/cerberus-ai/cerberus/releases/tag/v0.1.0
