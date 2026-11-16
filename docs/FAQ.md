# Frequently Asked Questions (FAQ)

**Version:** 0.1.0  
**Last Updated:** September 21, 2026

---

## General Questions

### What is Cerberus?

Cerberus is an intelligent code review system that uses multiple specialized AI agents to analyze your code from different perspectives: security, performance, and code quality. Unlike traditional static analysis tools that apply rigid rules, Cerberus uses Large Language Models (LLMs) to understand context and provide intelligent, actionable feedback.

### How is Cerberus different from traditional linters?

| Feature | Traditional Linters | Cerberus |
|---------|-------------------|--------------|
| **Analysis Type** | Rule-based, pattern matching | AI-powered, contextual understanding |
| **Explanations** | Error codes, brief messages | Natural language explanations with reasoning |
| **Context Awareness** | Limited | Understands code intent and broader context |
| **Learning** | Fixed rules | Can adapt prompts and improve over time |
| **Scope** | Single aspect (style, syntax) | Multi-aspect (security, performance, quality) |
| **False Positives** | Can be high | Lower due to contextual understanding |

**Best Practice**: Use both! Cerberus complements traditional linters, not replaces them.

### How is Cerberus different from GitHub Copilot?

GitHub Copilot helps you *write* code, while Cerberus helps you *review* code.

| Feature | GitHub Copilot | Cerberus |
|---------|---------------|--------------|
| **Primary Purpose** | Code generation/autocomplete | Code review/analysis |
| **Use Case** | Writing new code | Reviewing existing code |
| **Output** | Code suggestions | Security/performance/quality findings |
| **Timing** | While coding | Before commit, in CI/CD |

They solve different problems and complement each other well.

### Who is Cerberus for?

**Ideal Users:**
- Solo developers who want expert-level code review
- Small teams (2-10 developers) without dedicated reviewers
- Open-source maintainers reviewing community contributions
- Developers learning best practices in a new language

**Not Ideal For:**
- Large enterprises with complex compliance needs (yet—coming soon!)
- Teams that need 100% air-gapped solutions with zero LLM usage (use Ollama locally)

---

## Setup & Installation

### What are the system requirements?

**Minimum:**
- CPU: 2 cores
- RAM: 4GB
- Disk: 10GB free
- Docker 24.0+
- Docker Compose 2.20+

**Recommended:**
- CPU: 4+ cores
- RAM: 8GB+
- Disk: 20GB+ SSD
- Reliable internet (for cloud LLM providers)

### How long does setup take?

- **Quick Start (Docker Compose)**: 5 minutes
- **Production Deployment**: 1-2 hours
- **Custom Agent Development**: 3-4 hours

### Do I need an OpenAI API key?

No! While OpenAI provides the best quality, you have options:

1. **OpenAI** (recommended): $0.001-$0.03 per review depending on model
2. **Anthropic Claude**: Similar cost and quality to OpenAI
3. **Ollama** (local): Completely free, runs on your machine
4. **Azure OpenAI**: For enterprise customers with existing Azure contracts

### Can I run Cerberus completely offline?

Yes! Use Ollama for local LLM execution:

```yaml
llm:
  provider: ollama
  ollama:
    base_url: http://localhost:11434
    model: codellama
```

Your code never leaves your infrastructure. Quality is slightly lower than GPT-4 but still very useful.

### How do I update Cerberus?

```bash
# Pull latest version
docker-compose pull

# Backup database (important!)
docker-compose exec db pg_dump -U cerberus cerberus > backup.sql

# Restart with new version
docker-compose up -d

# Run migrations if needed
docker-compose exec api python -m cerberus.cli migrate
```

---

## Cost & Pricing

### How much does Cerberus cost?

**Cerberus Software**: Free and open-source (MIT License)

**LLM Costs** (variable):

| Provider | Model | Cost per Review | Notes |
|----------|-------|----------------|-------|
| OpenAI | GPT-4-turbo | ~$0.03 | Best quality |
| OpenAI | GPT-3.5-turbo | ~$0.001 | Good quality, very cheap |
| Anthropic | Claude 3 Sonnet | ~$0.015 | Excellent quality |
| Ollama | CodeLlama (local) | $0 | Free, runs locally |

**Example Monthly Costs** (assuming 20 reviews/day):
- With GPT-4: ~$18/month
- With GPT-3.5: ~$0.60/month
- With Ollama: $0/month

### How can I reduce LLM costs?

1. **Use caching**: Cerberus caches results (70%+ hit rate)
2. **Use cheaper models for some agents**:
   ```yaml
   agents:
     security:
       llm_model: gpt-4-turbo  # Most important
     performance:
       llm_model: gpt-3.5-turbo  # Cheaper
     quality:
       llm_model: gpt-3.5-turbo  # Cheaper
   ```
3. **Review only changed files** in CI/CD
4. **Use Ollama** for non-sensitive code
5. **Increase cache TTL** to 14+ days

### Is there a hosted/SaaS version?

Not yet, but it's on our roadmap! Currently, Cerberus is self-hosted only.

**Coming Soon:**
- Hosted version (cerberus.ai)
- Team collaboration features
- Historical trend analysis
- Priority support

Join our waitlist: https://cerberus.ai/waitlist

---

## Security & Privacy

### Is my code sent to OpenAI/Anthropic?

**Yes, if using cloud LLM providers.** Your code is sent to:
- OpenAI (if using GPT models)
- Anthropic (if using Claude models)
- Azure OpenAI (Microsoft's infrastructure)

**Data Retention:**
- OpenAI: 30 days (or zero-retention for enterprise)
- Anthropic: Not used for training
- Azure OpenAI: Customer-controlled

**For maximum privacy:** Use Ollama for local LLM execution—code never leaves your infrastructure.

### Is my code used to train AI models?

**No** (with cloud API usage). 

Both OpenAI and Anthropic have policies against using API data for training. However:
- Read their privacy policies carefully
- For sensitive code, use Ollama locally
- Consider Azure OpenAI for contractual guarantees

### How is my code stored in Cerberus?

By default:
- **Code content**: Not stored (only hash stored)
- **Review results**: Stored for 90 days
- **Logs**: Stored for 30 days
- **Metrics**: Aggregated, anonymized

You can configure:
```yaml
privacy:
  code_retention:
    enabled: false  # Don't store code
  review_retention:
    ttl_days: 30  # Keep results for 30 days instead of 90
```

### What about GDPR compliance?

Cerberus provides features for GDPR compliance:

- **Right to access**: Export user data
- **Right to deletion**: Delete user data
- **Right to portability**: Export in standard formats
- **Consent management**: Configurable consent requirements
- **Data minimization**: Only collect necessary data

**Important**: Review with your legal counsel. Compliance is a shared responsibility.

### Can Cerberus be used for PCI-DSS/SOC 2 compliance?

Yes, but:

1. **Self-hosted** with proper security controls
2. **Use local LLMs** (Ollama) to avoid data leaving infrastructure
3. **Enable audit logging** for compliance evidence
4. **Follow our Security Checklist**

We provide tools and documentation, but ultimate compliance is your responsibility. Consider hiring a compliance consultant.

---

## Usage & Features

### What programming languages are supported?

**All major languages**, including:
- Python, JavaScript/TypeScript, Java, Go, C++, C#, Ruby, PHP, Swift, Kotlin, Rust

Cerberus is **language-agnostic** because it uses LLMs that understand many languages. No language-specific parsers needed!

**Best Results**: Languages with more training data (Python, JavaScript, Java)

### How accurate is Cerberus?

**Security Agent**: ~95% accuracy on common vulnerabilities (OWASP Top 10)
**Performance Agent**: ~90% accuracy on algorithmic complexity
**Code Quality Agent**: Subjective, but provides valuable insights

**Note**: AI can have false positives/negatives. Always apply human judgment. Use as a helpful assistant, not absolute truth.

### How long does a review take?

**With cache hit**: <50ms (near-instant)
**Without cache**:
- Small file (<100 lines): 5-10 seconds
- Medium file (100-500 lines): 10-20 seconds
- Large file (500+ lines): 20-30 seconds

**Batch reviews**: Processed in parallel, ~10-15 seconds per file

**Slow review?** Check:
1. LLM provider response time
2. Network latency
3. Database query performance

### Can I review multiple files at once?

Yes! Use the batch endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/review/batch \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "files": [
      {"filename": "api.py", "code": "..."},
      {"filename": "utils.js", "code": "..."}
    ]
  }'
```

Files are processed in parallel for speed.

### Does Cerberus support incremental reviews?

Yes! Git hooks only review **changed files**:

```bash
# In pre-commit hook
STAGED_FILES=$(git diff --cached --name-only)

for FILE in $STAGED_FILES; do
  cerberus review --file "$FILE"
done
```

This is much faster than reviewing the entire codebase.

### Can I customize what agents check for?

Yes! Extensively customizable:

```yaml
agents:
  security:
    rule_sets:
      - owasp_top_10  # Enable/disable rule sets
    secret_scanning:
      custom_patterns:
        - regex: "API_KEY_[A-Z0-9]{32}"  # Custom patterns
    severity_mapping:
      hardcoded_credentials: critical  # Adjust severity
  
  performance:
    complexity:
      warn_at: "O(n²)"  # Custom thresholds
  
  quality:
    max_function_length: 50  # Custom limits
```

See [Configuration Reference](05-configuration-reference.md).

---

## Integration

### How do I integrate with CI/CD?

**GitHub Actions:**
```yaml
- name: Run Cerberus
  run: |
    cerberus-cli review --path . --format sarif > results.sarif
```

**GitLab CI:**
```yaml
cerberus:
  script:
    - cerberus-cli review --path . --format json
```

**Jenkins:**
```groovy
sh 'cerberus-cli review --path . --blocking'
```

See [Installation Guide - CI/CD Integration](04-installation-setup.md#common-integration-patterns).

### Can I integrate with Slack/Teams?

Yes! Use webhooks:

```python
# When review completes, send to Slack
webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK"
requests.post(webhook_url, json={
  "text": f"Review completed: {score}/100",
  "attachments": [{"text": format_findings(review)}]
})
```

See [Developer Guide - Example Projects](08-developer-guide.md#example-projects).

### Does Cerberus integrate with SonarQube?

Not directly, but you can export to SARIF format which SonarQube can import:

```bash
cerberus-cli review --format sarif > results.sarif
sonar-scanner -Dsonar.sarifReportPaths=results.sarif
```

### Can I use Cerberus with VS Code?

Yes! Community-contributed extensions available:

- **VS Code Extension**: [marketplace.visualstudio.com/cerberus](https://marketplace.visualstudio.com/cerberus)
- **JetBrains Plugin**: Coming soon

Or integrate via API:
```typescript
const result = await cerberusClient.review(activeEditor.document.getText());
```

---

## Troubleshooting

### Reviews are slow. How do I speed them up?

1. **Check cache hit rate**: Should be >70%
   ```bash
   curl http://localhost:9090/api/v1/query?query=cerberus_cache_hit_rate
   ```

2. **Use faster LLM models**:
   ```yaml
   llm:
     model: gpt-3.5-turbo  # Instead of gpt-4
   ```

3. **Reduce timeout if LLM is slow**:
   ```yaml
   agents:
     execution:
       timeout_seconds: 20  # Instead of 30
   ```

4. **Check LLM provider latency**:
   ```bash
   curl -s http://localhost:8000/api/v1/health?detailed=true | jq '.components.llm_providers'
   ```

### I'm getting "Rate limit exceeded" errors

**From LLM provider:**
- Upgrade OpenAI/Anthropic tier
- Add retry logic with exponential backoff
- Enable fallback providers

**From Cerberus:**
- Increase rate limits in config:
  ```yaml
  rate_limiting:
    per_key:
      requests_per_hour: 1000  # Increase from 100
  ```

### Git hook is not triggering

1. **Check hook exists and is executable**:
   ```bash
   ls -la .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

2. **Test hook manually**:
   ```bash
   .git/hooks/pre-commit
   ```

3. **Check API connectivity**:
   ```bash
   curl http://localhost:8000/api/v1/health
   ```

4. **Verify API key is set**:
   ```bash
   echo $CERBERUS_API_KEY
   ```

### Database connection errors

```bash
# Check database is running
docker-compose ps db

# Check connection
docker-compose exec db psql -U cerberus -c "SELECT 1"

# Restart database
docker-compose restart db
```

See [Troubleshooting Guide](06-monitoring-operations.md#troubleshooting-guide) for more scenarios.

---

## Advanced Topics

### Can I create custom agents?

Yes! See [Creating Custom Agents](08-developer-guide.md#creating-custom-agents).

Example custom agent:
```python
class TypeScriptLinterAgent(BaseAgent):
    async def analyze(self, code: str, context: dict) -> AgentResult:
        # Custom TypeScript-specific analysis
        pass
```

### How does caching work?

Cache key includes:
- Code content hash (SHA-256)
- Agent versions
- Configuration hash
- LLM model

If any of these change, cache is invalidated. Results stored in Redis with configurable TTL (default 7 days).

### Can I use multiple LLM providers simultaneously?

Yes! Route different agents to different providers:

```yaml
agents:
  security:
    llm_provider: openai  # Best quality for security
    llm_model: gpt-4-turbo
  
  performance:
    llm_provider: anthropic  # Alternative provider
    llm_model: claude-3-sonnet
  
  quality:
    llm_provider: ollama  # Free for quality checks
    llm_model: codellama
```

### How do I migrate from SQLite to PostgreSQL?

```bash
# Export from SQLite
cerberus-cli export --format sql > export.sql

# Update DATABASE_URL in .env
# DATABASE_URL=postgresql://...

# Import to PostgreSQL
docker-compose up -d db
cerberus-cli import < export.sql
```

---

## Contributing

### How can I contribute?

We welcome contributions!

1. **Code**: Fix bugs, add features
2. **Documentation**: Improve docs, add examples
3. **Testing**: Write tests, report bugs
4. **Community**: Help others, answer questions

See [Contributing Guidelines](08-developer-guide.md#contributing-guidelines).

### I found a bug. How do I report it?

1. **Check existing issues**: [GitHub Issues](https://github.com/cerberus-ai/cerberus/issues)
2. **Create new issue** with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Cerberus version
   - Environment details

### I have a feature request

1. **Check existing requests**: [GitHub Discussions](https://github.com/cerberus-ai/cerberus/discussions)
2. **Create new discussion** describing:
   - Use case
   - Desired behavior
   - Why existing features don't solve it

---

## Getting Help

Can't find your answer?

- 📚 **Documentation**: [docs.cerberus.ai](https://docs.cerberus.ai)
- 💬 **Discord**: [discord.gg/cerberus](https://discord.gg/cerberus)
- 📧 **Email**: support@cerberus.ai
- 🐛 **Issues**: [github.com/cerberus-ai/cerberus/issues](https://github.com/cerberus-ai/cerberus/issues)

---

**Last Updated**: September 21, 2026  
**Documentation Version**: 0.1.0
