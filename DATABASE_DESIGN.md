# Database Design & Optimization Specification

Comprehensive architectural and implementation guide for the enterprise persistence and caching layer of the Cerberus multi-agent code review platform.

---

## 📋 Table of Contents

1. [Architectural Overview & Entity-Relationship Model](#1-architectural-overview--entity-relationship-model)
   - [System Architecture & Persistence Principles](#system-architecture--persistence-principles)
   - [Domain Entity Relationship Diagram](#domain-entity-relationship-diagram)
   - [Table Inventory & Data Classifications](#table-inventory--data-classifications)
2. [Complete PostgreSQL DDL Schemas](#2-complete-postgresql-ddl-schemas)
   - [Extensions & Initialization](#extensions--initialization)
   - [Core Domain Table DDL (11 Domain Tables + 3 Auxiliary Tables)](#core-domain-table-ddl)
     - [1. `reviews`](#1-reviews-table)
     - [2. `security_findings`](#2-security_findings-table)
     - [3. `performance_findings`](#3-performance_findings-table)
     - [4. `testing_findings`](#4-testing_findings-table)
     - [5. `compliance_results`](#5-compliance_results-table)
     - [6. `cost_analysis`](#6-cost_analysis-table)
     - [7. `accessibility_reports`](#7-accessibility_reports-table)
     - [8. `ml_predictions`](#8-ml_predictions-table)
     - [9. `team_expertise`](#9-team_expertise-table)
     - [10. `knowledge_base`](#10-knowledge_base-table)
     - [11. `metrics_history`](#11-metrics_history-table)
     - [Auxiliary 1: `api_keys`](#auxiliary-1-api_keys-table)
     - [Auxiliary 2: `custom_rules`](#auxiliary-2-custom_rules-table)
     - [Auxiliary 3: `review_feedback`](#auxiliary-3-review_feedback-table)
   - [Automatic Timestamp Update Trigger](#automatic-timestamp-update-trigger)
3. [Comprehensive Indexing Strategy](#3-comprehensive-indexing-strategy)
   - [Composite B-Tree Indexes for Query Paths](#composite-b-tree-indexes-for-query-paths)
   - [Generalized Inverted Indexes (GIN) for JSONB & Arrays](#generalized-inverted-indexes-gin-for-jsonb--arrays)
   - [Full-Text Search (FTS) Inverted Indexes](#full-text-search-fts-inverted-indexes)
4. [Relational Integrity & Check Constraints](#4-relational-integrity--check-constraints)
   - [Foreign Key Cascades & Deletion Policies](#foreign-key-cascades--deletion-policies)
   - [Data Domain Domain Check Constraints](#data-domain-check-constraints)
5. [Complete Sample Data Seed Statements](#5-complete-sample-data-seed-statements)
   - [Domain Table Sample Insertions (Tables 1-11)](#domain-table-sample-insertions)
   - [Auxiliary Table Sample Insertions](#auxiliary-table-sample-insertions)
6. [Alembic Asynchronous Migration Framework](#6-alembic-asynchronous-migration-framework)
   - [`alembic.ini` Configuration](#alembicini-configuration)
   - [`alembic/env.py` (Async Engine with NullPool)](#alembicenvpy)
   - [`alembic/versions/001_initial_schema.py` (`upgrade()` & `downgrade()`)](#alembicversions001_initial_schemapy)
7. [Disaster Recovery, Continuous Archiving & Backup Runbooks](#7-disaster-recovery-continuous-archiving--backup-runbooks)
   - [Continuous WAL Archiving Configuration (`postgresql.conf`)](#continuous-wal-archiving-configuration)
   - [Physical Base Backup Runbook (`daily_basebackup.sh`)](#physical-base-backup-runbook)
   - [Multi-Threaded Logical Backup Runbook (`hourly_pgdump.sh`)](#multi-threaded-logical-backup-runbook)
   - [Step-by-Step Point-in-Time Recovery (PITR) Runbook (8 Steps)](#step-by-step-point-in-time-recovery-pitr-runbook)
8. [Redis Distributed Caching Architecture & Keyspace Strategy](#8-redis-distributed-caching-architecture--keyspace-strategy)
   - [Keyspace Taxonomy & Key Hierarchy](#keyspace-taxonomy--key-hierarchy)
   - [High-Performance Serialization & Deduplication (`orjson`)](#high-performance-serialization--deduplication)
   - [Time-to-Live (TTL) Policy Matrix](#time-to-live-ttl-policy-matrix)
   - [Cache Invalidation & Consistency Matrix](#cache-invalidation--consistency-matrix)
9. [Enterprise High-Concurrency Connection Pooling Strategy](#9-enterprise-high-concurrency-connection-pooling-strategy)
   - [Client-Side `asyncpg` Engine Configuration (`session.py`)](#client-side-asyncpg-engine-configuration)
   - [Enterprise PgBouncer Configuration (`pgbouncer.ini`)](#enterprise-pgbouncer-configuration)
10. [Diagnostic Database Monitoring & Observability Queries](#10-diagnostic-database-monitoring--observability-queries)
    - [Query 1: Top 10 Slowest Executing Queries (`pg_stat_statements`)](#query-1-top-10-slowest-executing-queries)
    - [Query 2: Index Hit Ratio Analysis](#query-2-index-hit-ratio-analysis)
    - [Query 3: Buffer Cache Hit Ratio Analysis](#query-3-buffer-cache-hit-ratio-analysis)
    - [Query 4: Dead Tuples, Table Bloat & Vacuum Optimization](#query-4-dead-tuples-table-bloat--vacuum-optimization)
    - [Query 5: Active & Idle Connection State Analysis](#query-5-active--idle-connection-state-analysis)
    - [Query 6: Lock Contention & Transaction Blocking Analysis](#query-6-lock-contention--transaction-blocking-analysis)
11. [Summary & Next Document Pointer](#11-summary--next-document-pointer)

---

## 1. Architectural Overview & Entity-Relationship Model

### System Architecture & Persistence Principles

The Cerberus multi-agent platform leverages a hybrid persistence architecture combining **PostgreSQL 16+** for durable, ACID-compliant relational and semi-structured storage, and **Redis 7+** for sub-millisecond deduplication caching and distributed token bucket rate limiting.

Key database architectural principles include:
1. **Durable Orchestration State**: Every review execution is tracked with a primary UUID entity in the `reviews` table, supporting asynchronous job queues and idempotent retry mechanics.
2. **Normalized Multi-Agent Findings**: Findings generated by specialized agents (Security, Performance, Testing, Compliance, Cost, Accessibility, ML) are partitioned into specialized relational domain tables tied back to the primary review via cascading foreign keys.
3. **Hybrid Schema Topology**: Structured operational attributes (scores, lines, complexities, severities) use strongly typed relational columns with native range constraints. Deep hierarchical telemetry (coverage gaps, AST indicators, prediction vectors, ARIA nodes) is indexed inside binary JSON (`JSONB`) columns.
4. **Sub-Millisecond Query Response**: Multi-column composite B-trees, GIN indexes on JSONB/arrays, and GiST/tsvector full-text search indexes maintain sub-50ms query response times under high concurrency.
5. **Strict Temporal Integrity**: All audit timestamps store microsecond-accurate UTC timezone data (`TIMESTAMPTZ`), with automatic `updated_at` modification triggers.

### Domain Entity Relationship Diagram

```text
# File: docs/diagrams/entity_relationship.txt
+---------------------------------------------------------------------------------------------------+
|                                            reviews                                                |
|---------------------------------------------------------------------------------------------------|
| PK  id                          UUID                                                              |
|     github_pr_url               VARCHAR(500)                                                      |
|     github_repo_owner           VARCHAR(255)                                                      |
|     github_repo_name            VARCHAR(255)                                                      |
|     commit_hash                 VARCHAR(64)                                                       |
|     git_branch                  VARCHAR(255)                                                      |
|     file_path                   VARCHAR(500)                                                      |
|     language                    VARCHAR(50)                                                       |
|     code_snippet                TEXT                                                              |
|     status                      VARCHAR(20)   ['queued','processing','completed','failed',...]    |
|     overall_score               NUMERIC(5,2)  [0.00 - 100.00]                                     |
|     processing_time_ms          INTEGER                                                           |
|     urgency                     VARCHAR(20)   ['low','medium','high','critical']                  |
|     is_blocking                 BOOLEAN                                                           |
|     block_reason                TEXT                                                              |
|     approved_by                 VARCHAR(255)                                                      |
|     approved_at                 TIMESTAMPTZ                                                       |
|     results_json                JSONB                                                             |
|     created_at                  TIMESTAMPTZ                                                       |
|     updated_at                  TIMESTAMPTZ                                                       |
|     completed_at                TIMESTAMPTZ                                                       |
+---------------------------------------------------------------------------------------------------+
          | 1                     | 1                     | 1                     | 1
          |                       |                       |                       |
          | N (ON DELETE CASCADE) | N (ON DELETE CASCADE) | N (ON DELETE CASCADE) | N (ON DELETE CASCADE)
          v                       v                       v                       v
+-----------------------+ +-----------------------+ +-----------------------+ +-----------------------+
|   security_findings   | | performance_findings  | |   testing_findings    | |  compliance_results   |
|-----------------------| |-----------------------| |-----------------------| |-----------------------|
| PK id        UUID     | | PK id        UUID     | | PK id        UUID     | | PK id        UUID     |
| FK review_id UUID     | | FK review_id UUID     | | FK review_id UUID     | | FK review_id UUID     |
|    cwe_id    VARCHAR  | |    issue_type VARCHAR | |    line_cov  NUMERIC  | |    framework VARCHAR  |
|    cve_id    VARCHAR  | |    cur_comp   VARCHAR | |    br_cov    NUMERIC  | |    ctrl_id   VARCHAR  |
|    vuln_type VARCHAR  | |    rec_comp   VARCHAR | |    tgt_cov   NUMERIC  | |    status    VARCHAR  |
|    severity  VARCHAR  | |    line_num   INTEGER | |    mut_score NUMERIC  | |    severity  VARCHAR  |
|    cvss      NUMERIC  | |    impact     TEXT    | |    gaps      JSONB    | |    details   TEXT     |
|    line_num  INTEGER  | |    lat_ms     NUMERIC | |    recs      JSONB    | |    remed     TEXT     |
|    col_num   INTEGER  | |    cpu_pct    NUMERIC | |    flaky     JSONB    | |    audit_ts  TIMESTZ  |
|    snippet   TEXT     | |    reg_prob   NUMERIC | |    prop_cand JSONB    | +-----------------------+
|    remed     TEXT     | |    refactor   TEXT    | |    created   TIMESTZ  |
|    exploit   NUMERIC  | |    created    TIMESTZ | +-----------------------+
|    fp_prob   NUMERIC  | +-----------------------+
|    is_fixed  BOOLEAN  |
|    created   TIMESTZ  |
+-----------------------+
          | 1                     | 1                     | 1                     | 1
          |                       |                       |                       |
          | N (ON DELETE CASCADE) | N (ON DELETE CASCADE) | N (ON DELETE CASCADE) | 1 (ON DELETE CASCADE)
          v                       v                       v                       v
+-----------------------+ +-----------------------+ +-----------------------+ +-----------------------+
|     cost_analysis     | | accessibility_reports | |    ml_predictions     | |    review_feedback    |
|-----------------------| |-----------------------| |-----------------------| |-----------------------|
| PK id        UUID     | | PK id        UUID     | | PK id        UUID     | | PK id        UUID     |
| FK review_id UUID     | | FK review_id UUID     | | FK review_id UUID     | | FK review_id UUID(UQ) |
|    provider  VARCHAR  | |    standard  VARCHAR  | |    model     VARCHAR  | |    user_id   VARCHAR  |
|    est_usd   NUMERIC  | |    level     VARCHAR  | |    version   VARCHAR  | |    rating    INTEGER  |
|    savings   NUMERIC  | |    violations INT     | |    pred_type VARCHAR  | |    helpful   BOOLEAN  |
|    tokens    INTEGER  | |    contrast  JSONB    | |    risk_scr  NUMERIC  | |    fp_count  INTEGER  |
|    llm_cost  NUMERIC  | |    aria_viol JSONB    | |    conf_int  NUMERIC  | |    fn_count  INTEGER  |
|    opps      JSONB    | |    kb_nav    JSONB    | |    features  JSONB    | |    comments  TEXT     |
|    effort    VARCHAR  | |    screen_rd JSONB    | |    anomalies JSONB    | |    created   TIMESTZ  |
|    created   TIMESTZ  | |    score     NUMERIC  | |    vector    JSONB    | +-----------------------+
+-----------------------+ |    created   TIMESTZ  | |    pred_at   TIMESTZ  |
                          +-----------------------+ +-----------------------+

+-------------------------------------+   +-------------------------------------+   +-------------------------------------+
|           team_expertise            |   |           knowledge_base            |   |           metrics_history           |
|-------------------------------------|   |-------------------------------------|   |-------------------------------------|
| PK id               UUID            |   | PK id               UUID            |   | PK id               UUID            |
|    team_id          VARCHAR(100)    |   |    category         VARCHAR(100)    |   |    repo_owner       VARCHAR(255)    |
|    member_id        VARCHAR(100)    |   |    pattern_key      VARCHAR(255)(UQ)|   |    repo_name        VARCHAR(255)    |
|    member_email     VARCHAR(255)    |   |    title            VARCHAR(255)    |   |    measurement_date DATE            |
|    member_name      VARCHAR(255)    |   |    problem_stmt     TEXT            |   |    total_reviews    INTEGER         |
|    primary_langs    TEXT[]          |   |    solution_pat     TEXT            |   |    avg_score        NUMERIC(5,2)    |
|    domains          TEXT[]          |   |    code_bad         TEXT            |   |    avg_security     NUMERIC(5,2)    |
|    experience_level VARCHAR(20)     |   |    code_good        TEXT            |   |    avg_coverage     NUMERIC(5,2)    |
|    capacity_per_day INTEGER         |   |    applicable_langs TEXT[]          |   |    avg_proc_time_ms INTEGER         |
|    active_reviews   INTEGER         |   |    tags             TEXT[]          |   |    tech_debt_score  NUMERIC(5,2)    |
|    last_assigned_at TIMESTAMPTZ     |   |    usage_count      INTEGER         |   |    critical_count   INTEGER         |
|    created_at       TIMESTAMPTZ     |   |    rating_positive  INTEGER         |   |    high_count       INTEGER         |
|    updated_at       TIMESTAMPTZ     |   |    rating_negative  INTEGER         |   |    cache_hit_rate   NUMERIC(5,2)    |
| UQ (team_id, member_id)             |   |    created_at       TIMESTAMPTZ     |   |    cost_savings_usd NUMERIC(12,2)   |
+-------------------------------------+   |    updated_at       TIMESTAMPTZ     |   |    created_at       TIMESTAMPTZ     |
                                          +-------------------------------------+   | UQ (repo_owner, repo_name, date)    |
                                                                                    +-------------------------------------+

+-------------------------------------+   +-------------------------------------+
|              api_keys               |   |            custom_rules             |
|-------------------------------------|   |-------------------------------------|
| PK id         UUID                  |   | PK id             UUID              |
|    key_hash   VARCHAR(128) (UQ)     |   |    name           VARCHAR(150) (UQ) |
|    name       VARCHAR(255)          |   |    description    TEXT              |
|    prefix     VARCHAR(16)           |   |    language       VARCHAR(50)       |
|    scopes     VARCHAR(255)          |   |    pattern        TEXT              |
|    is_active  BOOLEAN               |   |    rule_type      VARCHAR(30)       |
|    created_at TIMESTAMPTZ           |   |    severity       VARCHAR(20)       |
|    expires_at TIMESTAMPTZ           |   |    remediation    TEXT              |
+-------------------------------------+   |    is_active      BOOLEAN           |
                                          |    created_at     TIMESTAMPTZ       |
                                          |    updated_at     TIMESTAMPTZ       |
                                          +-------------------------------------+
```

### Table Inventory & Data Classifications

| # | Table Name | Cardinality / Volume | Retention Policy | Primary Storage Engine | Security / Compliance Classification |
|---|------------|----------------------|------------------|------------------------|---------------------------------------|
| 1 | `reviews` | High (100K - 10M rows) | 3 Years Active | PostgreSQL Table | Confidential / Intellectual Property |
| 2 | `security_findings` | Very High (1M - 50M rows) | 3 Years Active | PostgreSQL Table | Restricted / Vulnerability Data |
| 3 | `performance_findings` | High (500K - 10M rows) | 3 Years Active | PostgreSQL Table | Internal Operational Data |
| 4 | `testing_findings` | Medium (100K - 5M rows) | 3 Years Active | PostgreSQL Table | Internal Operational Data |
| 5 | `compliance_results` | High (500K - 20M rows) | 7 Years (Audit) | PostgreSQL Table | SOC2 / HIPAA / PCI Regulated Data |
| 6 | `cost_analysis` | Medium (100K - 5M rows) | 3 Years Active | PostgreSQL Table | Financial / Cloud Infrastructure |
| 7 | `accessibility_reports` | Medium (50K - 2M rows) | 3 Years Active | PostgreSQL Table | Internal Compliance Data |
| 8 | `ml_predictions` | High (500K - 10M rows) | 1 Year Active | PostgreSQL Table | Internal Analytical Data |
| 9 | `team_expertise` | Low (100 - 10K rows) | Indefinite | PostgreSQL Table | Internal HR / Routing Metadata |
| 10 | `knowledge_base` | Low (1K - 50K rows) | Indefinite | PostgreSQL Table | Internal Knowledge Asset |
| 11 | `metrics_history` | Medium (10K - 500K rows) | 5 Years Aggregated | PostgreSQL Table | Executive Reporting / KPIs |
| 12 | `api_keys` | Low (100 - 5K rows) | Until Revocation | PostgreSQL Table | Critical Secret (Hashed Only) |
| 13 | `custom_rules` | Low (50 - 5K rows) | Indefinite | PostgreSQL Table | Internal Policy Definitions |
| 14 | `review_feedback` | Medium (50K - 2M rows) | 3 Years Active | PostgreSQL Table | Developer Sentiment Data |

---

## 2. Complete PostgreSQL DDL Schemas

Below is the complete, self-contained SQL DDL containing over 50 executable statements that provision extensions, custom types, all 11 domain tables, all 3 auxiliary tables, automatic update triggers, and table comments.

### Extensions & Initialization

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- PostgreSQL 16+ Enterprise DDL Specification
-- Database: cerberus_db
-- Encoding: UTF8

-- 1. Enable Cryptographic Utilities for Secure UUID Generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Enable pg_stat_statements for Query Diagnostics and Latency Profiling
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- 3. Enable btree_gin for Combined B-tree and Inverted Indexing
CREATE EXTENSION IF NOT EXISTS "btree_gin";
```

### Core Domain Table DDL

#### 1. `reviews` Table

The central aggregate entity storing code review jobs, orchestration statuses, quality scores, and synthesized results.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 1: Code Reviews (Primary State & Entity Store)
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_pr_url VARCHAR(500),
    github_repo_owner VARCHAR(255) NOT NULL,
    github_repo_name VARCHAR(255) NOT NULL,
    commit_hash VARCHAR(64),
    git_branch VARCHAR(255),
    file_path VARCHAR(500),
    language VARCHAR(50) NOT NULL DEFAULT 'python',
    code_snippet TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    overall_score NUMERIC(5, 2),
    processing_time_ms INTEGER,
    urgency VARCHAR(20) NOT NULL DEFAULT 'medium',
    is_blocking BOOLEAN NOT NULL DEFAULT FALSE,
    block_reason TEXT,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    results_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    -- Status validation check constraint
    CONSTRAINT chk_reviews_status CHECK (
        status IN ('queued', 'processing', 'completed', 'failed', 'blocked', 'approved')
    ),
    -- Urgency level validation
    CONSTRAINT chk_reviews_urgency CHECK (
        urgency IN ('low', 'medium', 'high', 'critical')
    ),
    -- Score boundary check constraint (0.00 to 100.00)
    CONSTRAINT chk_reviews_overall_score CHECK (
        overall_score IS NULL OR (overall_score >= 0.00 AND overall_score <= 100.00)
    ),
    -- Non-negative execution duration
    CONSTRAINT chk_reviews_processing_time CHECK (
        processing_time_ms IS NULL OR processing_time_ms >= 0
    )
);

COMMENT ON TABLE reviews IS 'Core entity recording source code review submissions, execution states, quality gates, and final scores.';
COMMENT ON COLUMN reviews.results_json IS 'Complete synthesized multi-agent report JSON containing categorized findings and agent execution summaries.';
```

#### 2. `security_findings` Table

Persists SAST, dependency vulnerability, and secrets detection results generated by the Security Agent.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 2: Security Findings
CREATE TABLE security_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    cwe_id VARCHAR(30),
    cve_id VARCHAR(30),
    vulnerability_type VARCHAR(255) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    cvss_score NUMERIC(3, 1),
    line_number INTEGER,
    column_number INTEGER,
    code_snippet TEXT,
    remediation TEXT NOT NULL,
    exploitability_score NUMERIC(4, 3),
    false_positive_probability NUMERIC(4, 3) NOT NULL DEFAULT 0.020,
    is_fixed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Severity categorization
    CONSTRAINT chk_security_severity CHECK (
        severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')
    ),
    -- CVSS score range (0.0 to 10.0)
    CONSTRAINT chk_security_cvss CHECK (
        cvss_score IS NULL OR (cvss_score >= 0.0 AND cvss_score <= 10.0)
    ),
    -- Line number must be positive
    CONSTRAINT chk_security_line_number CHECK (
        line_number IS NULL OR line_number >= 1
    ),
    -- Exploitability probability boundary
    CONSTRAINT chk_security_exploitability CHECK (
        exploitability_score IS NULL OR (exploitability_score >= 0.000 AND exploitability_score <= 1.000)
    ),
    -- False positive probability boundary
    CONSTRAINT chk_security_fp_prob CHECK (
        false_positive_probability >= 0.000 AND false_positive_probability <= 1.000
    )
);

COMMENT ON TABLE security_findings IS 'Static security analysis findings, CWE/CVE mappings, CVSS risk scores, and suggested remediation code.';
```

#### 3. `performance_findings` Table

Stores algorithmic complexity analysis, resource bottleneck detections, and latency regression projections.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 3: Performance Findings
CREATE TABLE performance_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    issue_type VARCHAR(150) NOT NULL,
    current_complexity VARCHAR(50),
    recommended_complexity VARCHAR(50),
    line_number INTEGER,
    impact_description TEXT NOT NULL,
    estimated_latency_ms NUMERIC(10, 2),
    estimated_cpu_impact_pct NUMERIC(5, 2),
    regression_probability NUMERIC(4, 3),
    suggested_refactor TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Line number validation
    CONSTRAINT chk_perf_line_number CHECK (
        line_number IS NULL OR line_number >= 1
    ),
    -- Non-negative latency impact
    CONSTRAINT chk_perf_latency CHECK (
        estimated_latency_ms IS NULL OR estimated_latency_ms >= 0.00
    ),
    -- CPU impact percentage
    CONSTRAINT chk_perf_cpu CHECK (
        estimated_cpu_impact_pct IS NULL OR (estimated_cpu_impact_pct >= 0.00 AND estimated_cpu_impact_pct <= 100.00)
    ),
    -- Regression probability boundary
    CONSTRAINT chk_perf_regression_prob CHECK (
        regression_probability IS NULL OR (regression_probability >= 0.000 AND regression_probability <= 1.000)
    )
);

COMMENT ON TABLE performance_findings IS 'Algorithmic complexity regressions, memory leak warnings, and database access optimizations.';
```

#### 4. `testing_findings` Table

Records code coverage gaps, branch coverage metrics, mutation testing results, and property-based test candidates.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 4: Testing Findings
CREATE TABLE testing_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    line_coverage_pct NUMERIC(5, 2),
    branch_coverage_pct NUMERIC(5, 2),
    target_coverage_pct NUMERIC(5, 2) NOT NULL DEFAULT 80.00,
    mutation_score NUMERIC(4, 3),
    mutations_killed INTEGER DEFAULT 0,
    mutations_survived INTEGER DEFAULT 0,
    coverage_gaps JSONB DEFAULT '[]'::jsonb,
    test_recommendations JSONB DEFAULT '[]'::jsonb,
    flaky_test_risks JSONB DEFAULT '[]'::jsonb,
    property_test_candidates JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Percentage checks
    CONSTRAINT chk_test_line_cov CHECK (
        line_coverage_pct IS NULL OR (line_coverage_pct >= 0.00 AND line_coverage_pct <= 100.00)
    ),
    CONSTRAINT chk_test_branch_cov CHECK (
        branch_coverage_pct IS NULL OR (branch_coverage_pct >= 0.00 AND branch_coverage_pct <= 100.00)
    ),
    CONSTRAINT chk_test_target_cov CHECK (
        target_coverage_pct >= 0.00 AND target_coverage_pct <= 100.00
    ),
    CONSTRAINT chk_test_mutation_score CHECK (
        mutation_score IS NULL OR (mutation_score >= 0.000 AND mutation_score <= 1.000)
    ),
    CONSTRAINT chk_test_mutations_killed CHECK (mutations_killed >= 0),
    CONSTRAINT chk_test_mutations_survived CHECK (mutations_survived >= 0)
);

COMMENT ON TABLE testing_findings IS 'Automated test suite quality metrics, uncovered branch paths, and synthesized test cases.';
```

#### 5. `compliance_results` Table

Maintains audit-grade validation records for regulatory and enterprise frameworks (SOC2, HIPAA, PCI-DSS, ISO27001, GDPR).

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 5: Compliance Results
CREATE TABLE compliance_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    framework VARCHAR(50) NOT NULL,
    control_id VARCHAR(50) NOT NULL,
    control_description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    violation_details TEXT,
    remediation_steps TEXT,
    audit_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Supported regulatory frameworks
    CONSTRAINT chk_compliance_framework CHECK (
        framework IN ('SOC2', 'HIPAA', 'PCI-DSS', 'ISO27001', 'GDPR')
    ),
    -- Control evaluation status
    CONSTRAINT chk_compliance_status CHECK (
        status IN ('PASS', 'FAIL', 'WARN', 'NOT_APPLICABLE')
    ),
    -- Severity categorization
    CONSTRAINT chk_compliance_severity CHECK (
        severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')
    )
);

COMMENT ON TABLE compliance_results IS 'Audit-grade verification trail evaluating source code against international regulatory security controls.';
```

#### 6. `cost_analysis` Table

Forecasts monthly cloud infrastructure expenditure changes and LLM token usage resulting from code changes.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 6: Cost Analysis
CREATE TABLE cost_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    cloud_provider VARCHAR(50) NOT NULL DEFAULT 'aws',
    monthly_cost_estimate_usd NUMERIC(12, 4) DEFAULT 0.0000,
    estimated_savings_usd NUMERIC(12, 4) DEFAULT 0.0000,
    llm_token_count INTEGER DEFAULT 0,
    llm_cost_usd NUMERIC(8, 4) DEFAULT 0.0000,
    cost_optimization_opportunities JSONB DEFAULT '[]'::jsonb,
    implementation_effort VARCHAR(20) DEFAULT 'MEDIUM',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Cloud provider whitelist
    CONSTRAINT chk_cost_provider CHECK (
        cloud_provider IN ('aws', 'gcp', 'azure', 'ibm_cloud', 'llm')
    ),
    -- Non-negative monetary amounts
    CONSTRAINT chk_cost_monthly CHECK (monthly_cost_estimate_usd >= 0.0000),
    CONSTRAINT chk_cost_savings CHECK (estimated_savings_usd >= 0.0000),
    CONSTRAINT chk_cost_token_count CHECK (llm_token_count >= 0),
    CONSTRAINT chk_cost_llm_cost CHECK (llm_cost_usd >= 0.0000),
    CONSTRAINT chk_cost_effort CHECK (
        implementation_effort IN ('LOW', 'MEDIUM', 'HIGH')
    )
);

COMMENT ON TABLE cost_analysis IS 'Financial forecasting of cloud compute, storage, egress, and LLM token expenditures.';
```

#### 7. `accessibility_reports` Table

Audits user interface and front-end markup against WCAG 2.2 AA/AAA guidelines, ARIA specifications, and screen reader standards.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 7: Accessibility Reports
CREATE TABLE accessibility_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    wcag_standard VARCHAR(30) NOT NULL DEFAULT 'WCAG 2.2',
    conformance_level VARCHAR(10) NOT NULL DEFAULT 'AA',
    violation_count INTEGER NOT NULL DEFAULT 0,
    contrast_issues JSONB DEFAULT '[]'::jsonb,
    aria_violations JSONB DEFAULT '[]'::jsonb,
    keyboard_nav_issues JSONB DEFAULT '[]'::jsonb,
    screen_reader_issues JSONB DEFAULT '[]'::jsonb,
    overall_accessibility_score NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- WCAG conformance level
    CONSTRAINT chk_a11y_level CHECK (
        conformance_level IN ('A', 'AA', 'AAA')
    ),
    -- Non-negative violation count
    CONSTRAINT chk_a11y_violations CHECK (violation_count >= 0),
    -- Score range (0.00 to 100.00)
    CONSTRAINT chk_a11y_score CHECK (
        overall_accessibility_score IS NULL OR (overall_accessibility_score >= 0.00 AND overall_accessibility_score <= 100.00)
    )
);

COMMENT ON TABLE accessibility_reports IS 'WCAG 2.2 accessibility conformance audits, color contrast violations, and ARIA semantic issues.';
```

#### 8. `ml_predictions` Table

Stores machine learning inference results including defect probabilities, anomalous code patterns, and confidence intervals.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 8: ML Predictions
CREATE TABLE ml_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    prediction_type VARCHAR(50) NOT NULL,
    risk_score NUMERIC(4, 3) NOT NULL,
    confidence_interval NUMERIC(4, 3),
    features_used JSONB NOT NULL DEFAULT '{}'::jsonb,
    anomaly_indicators JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_prediction_vector JSONB,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Risk score between 0.000 and 1.000
    CONSTRAINT chk_ml_risk_score CHECK (
        risk_score >= 0.000 AND risk_score <= 1.000
    ),
    -- Confidence interval boundary
    CONSTRAINT chk_ml_confidence CHECK (
        confidence_interval IS NULL OR (confidence_interval >= 0.000 AND confidence_interval <= 1.000)
    )
);

COMMENT ON TABLE ml_predictions IS 'Machine learning predictive defect ratings, post-release regression odds, and feature attribution.';
```

#### 9. `team_expertise` Table

Maintains developer technical domain profiles, language proficiencies, and review capacity for intelligent reviewer routing.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 9: Team Expertise
CREATE TABLE team_expertise (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id VARCHAR(100) NOT NULL,
    member_id VARCHAR(100) NOT NULL,
    member_email VARCHAR(255) NOT NULL,
    member_name VARCHAR(255) NOT NULL,
    primary_languages TEXT[] NOT NULL DEFAULT '{}',
    domains TEXT[] NOT NULL DEFAULT '{}',
    experience_level VARCHAR(20) NOT NULL DEFAULT 'SENIOR',
    review_capacity_per_day INTEGER NOT NULL DEFAULT 5,
    active_reviews_count INTEGER NOT NULL DEFAULT 0,
    last_assigned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Experience level constraint
    CONSTRAINT chk_expertise_level CHECK (
        experience_level IN ('JUNIOR', 'MID', 'SENIOR', 'STAFF', 'PRINCIPAL')
    ),
    -- Positive capacity
    CONSTRAINT chk_expertise_capacity CHECK (review_capacity_per_day > 0),
    -- Non-negative active count
    CONSTRAINT chk_expertise_active_count CHECK (active_reviews_count >= 0),
    -- Unique member per team
    CONSTRAINT uq_team_expertise_member UNIQUE (team_id, member_id)
);

COMMENT ON TABLE team_expertise IS 'Developer domain mastery profiles and dynamic review bandwidth used for smart PR reviewer routing.';
```

#### 10. `knowledge_base` Table

Stores curated architectural anti-patterns, recommended coding solutions, and organizational standard patterns.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 10: Knowledge Base
CREATE TABLE knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category VARCHAR(100) NOT NULL,
    pattern_key VARCHAR(255) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    problem_statement TEXT NOT NULL,
    solution_pattern TEXT NOT NULL,
    code_example_bad TEXT,
    code_example_good TEXT,
    applicable_languages TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    usage_count INTEGER NOT NULL DEFAULT 0,
    rating_positive INTEGER NOT NULL DEFAULT 0,
    rating_negative INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Usage and rating bounds
    CONSTRAINT chk_kb_usage_count CHECK (usage_count >= 0),
    CONSTRAINT chk_kb_rating_pos CHECK (rating_positive >= 0),
    CONSTRAINT chk_kb_rating_neg CHECK (rating_negative >= 0)
);

COMMENT ON TABLE knowledge_base IS 'Organizational engineering standards, anti-patterns, and golden code solutions linked by agents.';
```

#### 11. `metrics_history` Table

Aggregates daily repository-level code quality KPIs, vulnerability counts, and technical debt trajectories.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Table 11: Metrics History
CREATE TABLE metrics_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_owner VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    measurement_date DATE NOT NULL,
    total_reviews_count INTEGER NOT NULL DEFAULT 0,
    avg_overall_score NUMERIC(5, 2),
    avg_security_score NUMERIC(5, 2),
    avg_test_coverage NUMERIC(5, 2),
    avg_processing_time_ms INTEGER,
    technical_debt_score NUMERIC(5, 2),
    critical_findings_count INTEGER NOT NULL DEFAULT 0,
    high_findings_count INTEGER NOT NULL DEFAULT 0,
    cache_hit_rate NUMERIC(5, 2),
    cost_savings_total_usd NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Score checks
    CONSTRAINT chk_metrics_total_reviews CHECK (total_reviews_count >= 0),
    CONSTRAINT chk_metrics_overall_score CHECK (
        avg_overall_score IS NULL OR (avg_overall_score >= 0.00 AND avg_overall_score <= 100.00)
    ),
    CONSTRAINT chk_metrics_security_score CHECK (
        avg_security_score IS NULL OR (avg_security_score >= 0.00 AND avg_security_score <= 100.00)
    ),
    CONSTRAINT chk_metrics_coverage CHECK (
        avg_test_coverage IS NULL OR (avg_test_coverage >= 0.00 AND avg_test_coverage <= 100.00)
    ),
    CONSTRAINT chk_metrics_debt_score CHECK (
        technical_debt_score IS NULL OR (technical_debt_score >= 0.00 AND technical_debt_score <= 100.00)
    ),
    CONSTRAINT chk_metrics_crit_count CHECK (critical_findings_count >= 0),
    CONSTRAINT chk_metrics_high_count CHECK (high_findings_count >= 0),
    CONSTRAINT chk_metrics_cache_hit CHECK (
        cache_hit_rate IS NULL OR (cache_hit_rate >= 0.00 AND cache_hit_rate <= 100.00)
    ),
    CONSTRAINT chk_metrics_cost_savings CHECK (cost_savings_total_usd >= 0.00),
    -- Unique constraint per repo per day
    CONSTRAINT uq_repo_measurement_date UNIQUE (repo_owner, repo_name, measurement_date)
);

COMMENT ON TABLE metrics_history IS 'Daily historical snapshot rollups tracking repository code quality trends over time.';
```

#### Auxiliary 1: `api_keys` Table

Authenticates programmatic clients via salted cryptographic SHA-256 hashes of client bearer tokens.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Auxiliary Table 1: API Keys (Authentication Store)
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(128) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    prefix VARCHAR(16) NOT NULL,
    scopes VARCHAR(255) NOT NULL DEFAULT 'review:read,review:write',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

COMMENT ON TABLE api_keys IS 'Hashed API credentials with role-based scopes (review:read, review:write, admin). Plaintext tokens are never stored.';
```

#### Auxiliary 2: `custom_rules` Table

User-defined AST, Semgrep, and regex pattern detection rules executed during code analysis.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Auxiliary Table 2: Custom Rules
CREATE TABLE custom_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    language VARCHAR(50) NOT NULL DEFAULT 'all',
    pattern TEXT NOT NULL,
    rule_type VARCHAR(30) NOT NULL DEFAULT 'ast_pattern',
    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    remediation_template TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Rule syntax category
    CONSTRAINT chk_custom_rule_type CHECK (
        rule_type IN ('ast_pattern', 'regex', 'semgrep_yaml')
    ),
    -- Severity categorization
    CONSTRAINT chk_custom_rule_severity CHECK (
        severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')
    )
);

COMMENT ON TABLE custom_rules IS 'Custom organization AST patterns and Semgrep detection rules.';
```

#### Auxiliary 3: `review_feedback` Table

Captures developer feedback, satisfaction ratings, and false-positive flags used to fine-tune review agents.

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Auxiliary Table 3: Review Feedback
CREATE TABLE review_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL UNIQUE REFERENCES reviews(id) ON DELETE CASCADE,
    user_id VARCHAR(255),
    rating INTEGER NOT NULL,
    is_helpful BOOLEAN NOT NULL DEFAULT TRUE,
    false_positives INTEGER NOT NULL DEFAULT 0,
    false_negatives INTEGER NOT NULL DEFAULT 0,
    comments TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 1 to 5 star rating
    CONSTRAINT chk_feedback_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT chk_feedback_fp CHECK (false_positives >= 0),
    CONSTRAINT chk_feedback_fn CHECK (false_negatives >= 0)
);

COMMENT ON TABLE review_feedback IS 'Developer ratings and accuracy feedback tied to specific review jobs.';
```

### Automatic Timestamp Update Trigger

```sql
-- # File: src/db/migrations/001_initial_schema.sql
-- Shared procedure to maintain accurate updated_at timestamps
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for reviews table
CREATE TRIGGER trg_update_reviews_timestamp
    BEFORE UPDATE ON reviews
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- Trigger for team_expertise table
CREATE TRIGGER trg_update_team_expertise_timestamp
    BEFORE UPDATE ON team_expertise
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- Trigger for knowledge_base table
CREATE TRIGGER trg_update_knowledge_base_timestamp
    BEFORE UPDATE ON knowledge_base
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();

-- Trigger for custom_rules table
CREATE TRIGGER trg_update_custom_rules_timestamp
    BEFORE UPDATE ON custom_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();
```

---

## 3. Comprehensive Indexing Strategy

To guarantee sub-50ms read latency at scale, multi-column composite B-trees, GIN indexes for JSONB and array attributes, and GiST/tsvector full-text search indexes are deployed.

### Composite B-Tree Indexes for Query Paths

```sql
-- # File: src/db/migrations/001_initial_schema.sql

-- 1. Repository-level active review queries with chronological sorting
CREATE INDEX idx_reviews_repo_status_created 
    ON reviews (github_repo_owner, github_repo_name, status, created_at DESC);

-- 2. System-wide review queue polling and status monitoring
CREATE INDEX idx_reviews_status_created 
    ON reviews (status, created_at DESC);

-- 3. Partial index for fast lookups by GitHub Pull Request URL
CREATE INDEX idx_reviews_pr_url 
    ON reviews (github_pr_url) 
    WHERE github_pr_url IS NOT NULL;

-- 4. Security findings filtered by review and severity (e.g. finding critical blockers)
CREATE INDEX idx_security_review_severity 
    ON security_findings (review_id, severity);

-- 5. Vulnerability vulnerability lookup by CWE and severity
CREATE INDEX idx_security_cwe_severity 
    ON security_findings (cwe_id, severity) 
    WHERE cwe_id IS NOT NULL;

-- 6. Performance findings sorted by highest estimated latency regression
CREATE INDEX idx_perf_review_latency 
    ON performance_findings (review_id, estimated_latency_ms DESC);

-- 7. Compliance audits filtered by framework and evaluation status
CREATE INDEX idx_compliance_review_framework 
    ON compliance_results (review_id, framework, status);

-- 8. Historical repository KPI time-series lookup
CREATE INDEX idx_metrics_repo_date 
    ON metrics_history (repo_owner, repo_name, measurement_date DESC);

-- 9. Knowledge base category and pattern lookup
CREATE INDEX idx_kb_category_pattern 
    ON knowledge_base (category, pattern_key);

-- 10. Intelligent reviewer routing query (least loaded available developer)
CREATE INDEX idx_team_expertise_routing 
    ON team_expertise (team_id, experience_level, active_reviews_count);

-- 11. Custom rule filtering by language and activation status
CREATE INDEX idx_custom_rules_lang_active 
    ON custom_rules (language, is_active);

-- 12. API key authentication lookups
CREATE INDEX idx_api_keys_active_hash 
    ON api_keys (key_hash) 
    WHERE is_active = TRUE;
```

### Generalized Inverted Indexes (GIN) for JSONB & Arrays

```sql
-- # File: src/db/migrations/001_initial_schema.sql

-- JSONB GIN Indexes for deep property filtering
CREATE INDEX idx_reviews_results_gin ON reviews USING GIN (results_json);
CREATE INDEX idx_testing_gaps_gin ON testing_findings USING GIN (coverage_gaps);
CREATE INDEX idx_testing_recommendations_gin ON testing_findings USING GIN (test_recommendations);
CREATE INDEX idx_cost_opportunities_gin ON cost_analysis USING GIN (cost_optimization_opportunities);
CREATE INDEX idx_a11y_contrast_gin ON accessibility_reports USING GIN (contrast_issues);
CREATE INDEX idx_a11y_aria_gin ON accessibility_reports USING GIN (aria_violations);
CREATE INDEX idx_ml_features_gin ON ml_predictions USING GIN (features_used);
CREATE INDEX idx_ml_anomalies_gin ON ml_predictions USING GIN (anomaly_indicators);

-- Array GIN Indexes for fast containment searches (e.g. domains @> ARRAY['security'])
CREATE INDEX idx_team_languages_gin ON team_expertise USING GIN (primary_languages);
CREATE INDEX idx_team_domains_gin ON team_expertise USING GIN (domains);
CREATE INDEX idx_kb_languages_gin ON knowledge_base USING GIN (applicable_languages);
CREATE INDEX idx_kb_tags_gin ON knowledge_base USING GIN (tags);
```

### Full-Text Search (FTS) Inverted Indexes

```sql
-- # File: src/db/migrations/001_initial_schema.sql

-- Knowledge Base Full-Text Search across Title, Problem Statement, and Solution
CREATE INDEX idx_kb_fts ON knowledge_base 
    USING GIN (to_tsvector('english', title || ' ' || problem_statement || ' ' || solution_pattern));

-- Security Findings Full-Text Search across Remediation Instructions
CREATE INDEX idx_security_remediation_fts ON security_findings 
    USING GIN (to_tsvector('english', remediation));
```

---

## 4. Relational Integrity & Check Constraints

### Foreign Key Cascades & Deletion Policies

Relational integrity guarantees that deleting a review cleans up all associated child findings, while reference and governance records remain protected:

| Foreign Key | Parent Table | Child Table | Deletion Rule | Update Rule | Rationale |
|-------------|--------------|-------------|---------------|-------------|-----------|
| `review_id` | `reviews` | `security_findings` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `performance_findings` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `testing_findings` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `compliance_results` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `cost_analysis` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `accessibility_reports` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `ml_predictions` | `ON DELETE CASCADE` | `CASCADE` | Findings are strictly owned by their parent review lifecycle. |
| `review_id` | `reviews` | `review_feedback` | `ON DELETE CASCADE` | `CASCADE` | Feedback is directly bound to the review session. |

### Data Domain Check Constraints

The database enforces data cleanliness at the persistence boundary:
- **Scores**: Numeric bounds `[0.00, 100.00]` prevent out-of-range quality indicators across `reviews`, `testing_findings`, `accessibility_reports`, and `metrics_history`.
- **Probabilities & CVSS**: `cvss_score BETWEEN 0.0 AND 10.0`; all probabilities (`exploitability_score`, `false_positive_probability`, `regression_probability`, `risk_score`) constrained to `[0.000, 1.000]`.
- **Enumerations**: Validated via inline SQL `CHECK (... IN (...))` constraints, guaranteeing that only recognized status values enter the system without requiring complex PostgreSQL enum migration overhead.

---

## 5. Complete Sample Data Seed Statements

The following production-grade seed script populates all 11 domain tables and auxiliary tables with interconnected, realistic data for development, staging, and automated integration testing.

### Domain Table Sample Insertions

```sql
-- # File: src/db/seeds/001_sample_data.sql
-- Seed Data for Cerberus Integration & Staging

-- 1. Seed: reviews
INSERT INTO reviews (
    id, github_pr_url, github_repo_owner, github_repo_name, commit_hash, 
    git_branch, file_path, language, code_snippet, status, overall_score, 
    processing_time_ms, urgency, is_blocking, block_reason, approved_by, 
    approved_at, results_json, created_at, updated_at, completed_at
) VALUES (
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'https://github.com/enterprise-org/payment-gateway/pull/402',
    'enterprise-org',
    'payment-gateway',
    'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
    'feature/checkout-flow',
    'src/services/billing.py',
    'python',
    'def process_charge(user_id, amount):\n    cursor.execute(f"UPDATE accounts SET balance = balance - {amount} WHERE user_id = \'{user_id}\'")',
    'completed',
    64.50,
    3420,
    'high',
    TRUE,
    'Critical SQL injection detected in billing transaction handler',
    NULL,
    NULL,
    '{
        "summary": "Critical SQL injection and unhandled timeout detected",
        "agents_executed": ["security", "performance", "testing", "compliance", "cost", "accessibility", "ml"],
        "findings_count": {
            "critical": 1,
            "high": 1,
            "medium": 2,
            "low": 1
        }
    }'::jsonb,
    NOW() - INTERVAL '1 hour',
    NOW() - INTERVAL '58 minutes',
    NOW() - INTERVAL '58 minutes'
);

-- 2. Seed: security_findings
INSERT INTO security_findings (
    id, review_id, cwe_id, cve_id, vulnerability_type, severity, cvss_score, 
    line_number, column_number, code_snippet, remediation, exploitability_score, 
    false_positive_probability, is_fixed, created_at
) VALUES (
    '9a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'CWE-89',
    'CVE-2024-9999',
    'SQL Injection Vulnerability',
    'CRITICAL',
    9.8,
    2,
    19,
    'cursor.execute(f"UPDATE accounts SET balance = balance - {amount} WHERE user_id = \'{user_id}\'")',
    'Utilize parameterized query binding: cursor.execute("UPDATE accounts SET balance = balance - %s WHERE user_id = %s", (amount, user_id))',
    0.950,
    0.010,
    FALSE,
    NOW() - INTERVAL '58 minutes'
);

-- 3. Seed: performance_findings
INSERT INTO performance_findings (
    id, review_id, issue_type, current_complexity, recommended_complexity, 
    line_number, impact_description, estimated_latency_ms, estimated_cpu_impact_pct, 
    regression_probability, suggested_refactor, created_at
) VALUES (
    '1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'Unbounded Connection Loop',
    'O(N)',
    'O(1)',
    1,
    'Serial database transaction execution inside request handler without connection pooling degrades throughput by 45%',
    125.40,
    32.50,
    0.850,
    'Batch the charge operations into an atomic multi-row statement using asyncpg executemany.',
    NOW() - INTERVAL '58 minutes'
);

-- 4. Seed: testing_findings
INSERT INTO testing_findings (
    id, review_id, line_coverage_pct, branch_coverage_pct, target_coverage_pct, 
    mutation_score, mutations_killed, mutations_survived, coverage_gaps, 
    test_recommendations, flaky_test_risks, property_test_candidates, created_at
) VALUES (
    '2b3c4d5e-6f7a-8b9c-0d1e-2f3a4b5c6d7e',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    42.50,
    30.00,
    85.00,
    0.480,
    24,
    26,
    '["billing.py:process_charge:negative_amount_handling", "billing.py:process_charge:database_disconnect_retry"]'::jsonb,
    '[
        {"type": "unit", "description": "Verify ValueError raised on negative charge input"},
        {"type": "integration", "description": "Verify rollback on transient connection loss"}
    ]'::jsonb,
    '["test_billing_concurrent_charges: race condition on shared database fixture"]'::jsonb,
    '["@given(st.floats(min_value=-1000, max_value=0)) def test_invalid_amounts(amt): ..."]'::jsonb,
    NOW() - INTERVAL '58 minutes'
);

-- 5. Seed: compliance_results
INSERT INTO compliance_results (
    id, review_id, framework, control_id, control_description, status, 
    severity, violation_details, remediation_steps, audit_timestamp
) VALUES (
    '3c4d5e6f-7a8b-9c0d-1e2f-3a4b5c6d7e8f',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'PCI-DSS',
    'Req-6.5.1',
    'Injection flaws, particularly SQL injection, must be prevented by validating and sanitizing user inputs.',
    'FAIL',
    'CRITICAL',
    'Direct string interpolation detected in SQL statement interacting with cardholder balance ledger.',
    'Refactor to use prepared statements with strictly typed bind variables and enable query audit logging.',
    NOW() - INTERVAL '58 minutes'
);

-- 6. Seed: cost_analysis
INSERT INTO cost_analysis (
    id, review_id, cloud_provider, monthly_cost_estimate_usd, estimated_savings_usd, 
    llm_token_count, llm_cost_usd, cost_optimization_opportunities, implementation_effort, 
    created_at
) VALUES (
    '4d5e6f7a-8b9c-0d1e-2f3a-4b5c6d7e8f9a',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'aws',
    420.5000,
    180.0000,
    14500,
    0.0435,
    '[
        {"category": "compute", "action": "Migrate on-demand ECS task to Fargate Spot for non-critical queue processing", "projected_monthly_savings_usd": 120.00},
        {"category": "database", "action": "Enable Aurora I/O-optimized instance storage class", "projected_monthly_savings_usd": 60.00}
    ]'::jsonb,
    'MEDIUM',
    NOW() - INTERVAL '58 minutes'
);

-- 7. Seed: accessibility_reports
INSERT INTO accessibility_reports (
    id, review_id, wcag_standard, conformance_level, violation_count, 
    contrast_issues, aria_violations, keyboard_nav_issues, screen_reader_issues, 
    overall_accessibility_score, created_at
) VALUES (
    '5e6f7a8b-9c0d-1e2f-3a4b-5c6d7e8f9a0b',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'WCAG 2.2',
    'AA',
    2,
    '[{"element": "button#submit-payment", "ratio": "2.8:1", "required": "4.5:1", "fix": "Change text color from #888888 to #222222"}]'::jsonb,
    '[{"element": "div#payment-modal", "issue": "Missing aria-modal=true and role=dialog attributes"}]'::jsonb,
    '[]'::jsonb,
    '[]'::jsonb,
    78.00,
    NOW() - INTERVAL '58 minutes'
);

-- 8. Seed: ml_predictions
INSERT INTO ml_predictions (
    id, review_id, model_name, model_version, prediction_type, risk_score, 
    confidence_interval, features_used, anomaly_indicators, raw_prediction_vector, 
    predicted_at
) VALUES (
    '6f7a8b9c-0d1e-2f3a-4b5c-6d7e8f9a0b1c',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'DefectPredictor-GNN',
    'v2.4.1',
    'post_release_defect_probability',
    0.885,
    0.920,
    '{"cyclomatic_complexity": 14, "lines_changed": 48, "developer_experience_months": 8, "churn_rate": 0.42}'::jsonb,
    '["Unusually high cyclomatic complexity coupled with database call inside handler", "Modified critical financial domain path"]'::jsonb,
    '[0.885, 0.115]'::jsonb,
    NOW() - INTERVAL '58 minutes'
);

-- 9. Seed: team_expertise
INSERT INTO team_expertise (
    id, team_id, member_id, member_email, member_name, primary_languages, 
    domains, experience_level, review_capacity_per_day, active_reviews_count, 
    last_assigned_at, created_at, updated_at
) VALUES (
    '7a8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d',
    'payments-core',
    'usr_dev_441',
    'alex.chen@enterprise.corp',
    'Alex Chen',
    ARRAY['python', 'sql', 'go'],
    ARRAY['security', 'pci_compliance', 'distributed_systems'],
    'STAFF',
    6,
    2,
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '30 days',
    NOW() - INTERVAL '2 hours'
);

-- 10. Seed: knowledge_base
INSERT INTO knowledge_base (
    id, category, pattern_key, title, problem_statement, solution_pattern, 
    code_example_bad, code_example_good, applicable_languages, tags, 
    usage_count, rating_positive, rating_negative, created_at, updated_at
) VALUES (
    '8b9c0d1e-2f3a-4b5c-6d7e-8f9a0b1c2d3e',
    'security',
    'SEC-SQLI-PYTHON-PARAMETRIZATION',
    'Safe SQL Query Execution via Parameterized Bindings',
    'Direct f-string or format-string concatenation into SQL statements exposes database engines to second-order and first-order SQL injection.',
    'Always pass SQL statements as static strings with placeholder tokens and supply values separately as parameters.',
    'cursor.execute(f"SELECT * FROM users WHERE email = \'{email}\'")',
    'cursor.execute("SELECT * FROM users WHERE email = %s", (email,))',
    ARRAY['python', 'sql'],
    ARRAY['security', 'cwe-89', 'owasp-top-10', 'database'],
    142,
    98,
    2,
    NOW() - INTERVAL '60 days',
    NOW() - INTERVAL '1 day'
);

-- 11. Seed: metrics_history
INSERT INTO metrics_history (
    id, repo_owner, repo_name, measurement_date, total_reviews_count, 
    avg_overall_score, avg_security_score, avg_test_coverage, avg_processing_time_ms, 
    technical_debt_score, critical_findings_count, high_findings_count, 
    cache_hit_rate, cost_savings_total_usd, created_at
) VALUES (
    '9c0d1e2f-3a4b-5c6d-7e8f-9a0b1c2d3e4f',
    'enterprise-org',
    'payment-gateway',
    CURRENT_DATE - INTERVAL '1 day',
    38,
    86.20,
    91.40,
    82.75,
    2840,
    14.20,
    1,
    4,
    74.50,
    1450.00,
    NOW() - INTERVAL '1 day'
);
```

### Auxiliary Table Sample Insertions

```sql
-- # File: src/db/seeds/001_sample_data.sql

-- Auxiliary Seed 1: api_keys
-- Pre-calculated SHA-256 hash for raw key 'cvai_live_8f7e6d5c4b3a2918e0f1a2b3c4d5e6f7'
INSERT INTO api_keys (
    id, key_hash, name, prefix, scopes, is_active, created_at, expires_at
) VALUES (
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e',
    'GitHub Actions CI/CD Integration',
    'cvai_',
    'review:read,review:write,admin',
    TRUE,
    NOW() - INTERVAL '15 days',
    NOW() + INTERVAL '350 days'
);

-- Auxiliary Seed 2: custom_rules
INSERT INTO custom_rules (
    id, name, description, language, pattern, rule_type, severity, 
    remediation_template, is_active, created_at, updated_at
) VALUES (
    'b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e',
    'DISALLOW_RAW_PRINT_IN_PRODUCTION',
    'Standard stdout print calls bypass centralized JSON structured logging and trace context.',
    'python',
    'print($...ARGS)',
    'semgrep_yaml',
    'MEDIUM',
    'Replace print() with logger.info() or logger.debug() importing from src.core.logging',
    TRUE,
    NOW() - INTERVAL '20 days',
    NOW() - INTERVAL '20 days'
);

-- Auxiliary Seed 3: review_feedback
INSERT INTO review_feedback (
    id, review_id, user_id, rating, is_helpful, false_positives, false_negatives, comments, created_at
) VALUES (
    'c3d4e5f6-a7b8-9c0d-1e2f-3a4b5c6d7e8f',
    '8f7e6d5c-4b3a-2918-a0c1-e2f3a4b5c6d7',
    'usr_dev_441',
    5,
    TRUE,
    0,
    0,
    'Caught the SQL injection vulnerability before staging deployment. Excellent parameterized suggestion.',
    NOW() - INTERVAL '30 minutes'
);
```

---

## 6. Alembic Asynchronous Migration Framework

The platform employs SQLAlchemy 2.0 and Alembic with native asynchronous database connectivity via `asyncpg`. In migration contexts, connection pooling is disabled using `pool.NullPool` to avoid lingering transactional locks.

### `alembic.ini` Configuration

```ini
# File: alembic.ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_locations = alembic/versions
version_path_separator = os

sqlalchemy.url = postgresql+asyncpg://cerberus:production_password@pgbouncer:6432/cerberus_db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

### `alembic/env.py`

```python
# File: alembic/env.py
"""Alembic asynchronous migration environment using asyncpg and NullPool."""
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Configuration & Logging setup
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import application Base metadata for autogenerate support
from src.models.database import Base
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    Generates raw static SQL DDL without opening a persistent connection.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run actual migration steps inside a synchronous connection block."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using asynchronous asyncpg engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entrypoint for online migrations executing in an asyncio event loop."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### `alembic/versions/001_initial_schema.py`

```python
# File: alembic/versions/001_initial_schema.py
"""Initial database schema migration covering all 11 domain tables, auxiliary tables, and indexes.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-09-24 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_stat_statements"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')

    # 1. Table: reviews
    op.create_table(
        'reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('github_pr_url', sa.String(length=500), nullable=True),
        sa.Column('github_repo_owner', sa.String(length=255), nullable=False),
        sa.Column('github_repo_name', sa.String(length=255), nullable=False),
        sa.Column('commit_hash', sa.String(length=64), nullable=True),
        sa.Column('git_branch', sa.String(length=255), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('language', sa.String(length=50), server_default='python', nullable=False),
        sa.Column('code_snippet', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('overall_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('urgency', sa.String(length=20), server_default='medium', nullable=False),
        sa.Column('is_blocking', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('block_reason', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('results_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed', 'blocked', 'approved')", name='chk_reviews_status'),
        sa.CheckConstraint("urgency IN ('low', 'medium', 'high', 'critical')", name='chk_reviews_urgency'),
        sa.CheckConstraint("overall_score IS NULL OR (overall_score >= 0.0 AND overall_score <= 100.0)", name='chk_reviews_overall_score'),
        sa.CheckConstraint("processing_time_ms IS NULL OR processing_time_ms >= 0", name='chk_reviews_processing_time'),
    )
    op.create_index('idx_reviews_repo_status_created', 'reviews', ['github_repo_owner', 'github_repo_name', 'status', sa.text('created_at DESC')])
    op.create_index('idx_reviews_status_created', 'reviews', ['status', sa.text('created_at DESC')])
    op.create_index('idx_reviews_pr_url', 'reviews', ['github_pr_url'], postgresql_where=sa.text('github_pr_url IS NOT NULL'))
    op.create_index('idx_reviews_results_gin', 'reviews', ['results_json'], postgresql_using='gin')

    # 2. Table: security_findings
    op.create_table(
        'security_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cwe_id', sa.String(length=30), nullable=True),
        sa.Column('cve_id', sa.String(length=30), nullable=True),
        sa.Column('vulnerability_type', sa.String(length=255), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('cvss_score', sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('column_number', sa.Integer(), nullable=True),
        sa.Column('code_snippet', sa.Text(), nullable=True),
        sa.Column('remediation', sa.Text(), nullable=False),
        sa.Column('exploitability_score', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('false_positive_probability', sa.Numeric(precision=4, scale=3), server_default='0.020', nullable=False),
        sa.Column('is_fixed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')", name='chk_security_severity'),
        sa.CheckConstraint("cvss_score IS NULL OR (cvss_score >= 0.0 AND cvss_score <= 10.0)", name='chk_security_cvss'),
        sa.CheckConstraint("line_number IS NULL OR line_number >= 1", name='chk_security_line_number'),
        sa.CheckConstraint("exploitability_score IS NULL OR (exploitability_score >= 0.0 AND exploitability_score <= 1.0)", name='chk_security_exploitability'),
        sa.CheckConstraint("false_positive_probability >= 0.0 AND false_positive_probability <= 1.0", name='chk_security_fp_prob'),
    )
    op.create_index('idx_security_review_severity', 'security_findings', ['review_id', 'severity'])
    op.create_index('idx_security_cwe_severity', 'security_findings', ['cwe_id', 'severity'], postgresql_where=sa.text('cwe_id IS NOT NULL'))
    op.execute("CREATE INDEX idx_security_remediation_fts ON security_findings USING GIN (to_tsvector('english', remediation))")

    # 3. Table: performance_findings
    op.create_table(
        'performance_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('issue_type', sa.String(length=150), nullable=False),
        sa.Column('current_complexity', sa.String(length=50), nullable=True),
        sa.Column('recommended_complexity', sa.String(length=50), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('impact_description', sa.Text(), nullable=False),
        sa.Column('estimated_latency_ms', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('estimated_cpu_impact_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('regression_probability', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('suggested_refactor', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("line_number IS NULL OR line_number >= 1", name='chk_perf_line_number'),
        sa.CheckConstraint("estimated_latency_ms IS NULL OR estimated_latency_ms >= 0.0", name='chk_perf_latency'),
        sa.CheckConstraint("estimated_cpu_impact_pct IS NULL OR (estimated_cpu_impact_pct >= 0.0 AND estimated_cpu_impact_pct <= 100.0)", name='chk_perf_cpu'),
        sa.CheckConstraint("regression_probability IS NULL OR (regression_probability >= 0.0 AND regression_probability <= 1.0)", name='chk_perf_regression_prob'),
    )
    op.create_index('idx_perf_review_latency', 'performance_findings', ['review_id', sa.text('estimated_latency_ms DESC')])

    # 4. Table: testing_findings
    op.create_table(
        'testing_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('line_coverage_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('branch_coverage_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('target_coverage_pct', sa.Numeric(precision=5, scale=2), server_default='80.00', nullable=False),
        sa.Column('mutation_score', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('mutations_killed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('mutations_survived', sa.Integer(), server_default='0', nullable=False),
        sa.Column('coverage_gaps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('test_recommendations', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('flaky_test_risks', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('property_test_candidates', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("line_coverage_pct IS NULL OR (line_coverage_pct >= 0.0 AND line_coverage_pct <= 100.0)", name='chk_test_line_cov'),
        sa.CheckConstraint("branch_coverage_pct IS NULL OR (branch_coverage_pct >= 0.0 AND branch_coverage_pct <= 100.0)", name='chk_test_branch_cov'),
        sa.CheckConstraint("target_coverage_pct >= 0.0 AND target_coverage_pct <= 100.0", name='chk_test_target_cov'),
        sa.CheckConstraint("mutation_score IS NULL OR (mutation_score >= 0.0 AND mutation_score <= 1.0)", name='chk_test_mutation_score'),
        sa.CheckConstraint("mutations_killed >= 0", name='chk_test_mutations_killed'),
        sa.CheckConstraint("mutations_survived >= 0", name='chk_test_mutations_survived'),
    )
    op.create_index('idx_testing_gaps_gin', 'testing_findings', ['coverage_gaps'], postgresql_using='gin')

    # 5. Table: compliance_results
    op.create_table(
        'compliance_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('framework', sa.String(length=50), nullable=False),
        sa.Column('control_id', sa.String(length=50), nullable=False),
        sa.Column('control_description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('violation_details', sa.Text(), nullable=True),
        sa.Column('remediation_steps', sa.Text(), nullable=True),
        sa.Column('audit_timestamp', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("framework IN ('SOC2', 'HIPAA', 'PCI-DSS', 'ISO27001', 'GDPR')", name='chk_compliance_framework'),
        sa.CheckConstraint("status IN ('PASS', 'FAIL', 'WARN', 'NOT_APPLICABLE')", name='chk_compliance_status'),
        sa.CheckConstraint("severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')", name='chk_compliance_severity'),
    )
    op.create_index('idx_compliance_review_framework', 'compliance_results', ['review_id', 'framework', 'status'])

    # 6. Table: cost_analysis
    op.create_table(
        'cost_analysis',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cloud_provider', sa.String(length=50), server_default='aws', nullable=False),
        sa.Column('monthly_cost_estimate_usd', sa.Numeric(precision=12, scale=4), server_default='0.0000', nullable=False),
        sa.Column('estimated_savings_usd', sa.Numeric(precision=12, scale=4), server_default='0.0000', nullable=False),
        sa.Column('llm_token_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('llm_cost_usd', sa.Numeric(precision=8, scale=4), server_default='0.0000', nullable=False),
        sa.Column('cost_optimization_opportunities', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('implementation_effort', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("cloud_provider IN ('aws', 'gcp', 'azure', 'ibm_cloud', 'llm')", name='chk_cost_provider'),
        sa.CheckConstraint("monthly_cost_estimate_usd >= 0.0", name='chk_cost_monthly'),
        sa.CheckConstraint("estimated_savings_usd >= 0.0", name='chk_cost_savings'),
        sa.CheckConstraint("llm_token_count >= 0", name='chk_cost_token_count'),
        sa.CheckConstraint("llm_cost_usd >= 0.0", name='chk_cost_llm_cost'),
        sa.CheckConstraint("implementation_effort IN ('LOW', 'MEDIUM', 'HIGH')", name='chk_cost_effort'),
    )
    op.create_index('idx_cost_opportunities_gin', 'cost_analysis', ['cost_optimization_opportunities'], postgresql_using='gin')

    # 7. Table: accessibility_reports
    op.create_table(
        'accessibility_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('wcag_standard', sa.String(length=30), server_default='WCAG 2.2', nullable=False),
        sa.Column('conformance_level', sa.String(length=10), server_default='AA', nullable=False),
        sa.Column('violation_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('contrast_issues', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('aria_violations', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('keyboard_nav_issues', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('screen_reader_issues', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('overall_accessibility_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("conformance_level IN ('A', 'AA', 'AAA')", name='chk_a11y_level'),
        sa.CheckConstraint("violation_count >= 0", name='chk_a11y_violations'),
        sa.CheckConstraint("overall_accessibility_score IS NULL OR (overall_accessibility_score >= 0.0 AND overall_accessibility_score <= 100.0)", name='chk_a11y_score'),
    )

    # 8. Table: ml_predictions
    op.create_table(
        'ml_predictions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('prediction_type', sa.String(length=50), nullable=False),
        sa.Column('risk_score', sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column('confidence_interval', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('features_used', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('anomaly_indicators', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('raw_prediction_vector', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('predicted_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name='chk_ml_risk_score'),
        sa.CheckConstraint("confidence_interval IS NULL OR (confidence_interval >= 0.0 AND confidence_interval <= 1.0)", name='chk_ml_confidence'),
    )
    op.create_index('idx_ml_features_gin', 'ml_predictions', ['features_used'], postgresql_using='gin')

    # 9. Table: team_expertise
    op.create_table(
        'team_expertise',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('team_id', sa.String(length=100), nullable=False),
        sa.Column('member_id', sa.String(length=100), nullable=False),
        sa.Column('member_email', sa.String(length=255), nullable=False),
        sa.Column('member_name', sa.String(length=255), nullable=False),
        sa.Column('primary_languages', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('domains', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('experience_level', sa.String(length=20), server_default='SENIOR', nullable=False),
        sa.Column('review_capacity_per_day', sa.Integer(), server_default='5', nullable=False),
        sa.Column('active_reviews_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'member_id', name='uq_team_expertise_member'),
        sa.CheckConstraint("experience_level IN ('JUNIOR', 'MID', 'SENIOR', 'STAFF', 'PRINCIPAL')", name='chk_expertise_level'),
        sa.CheckConstraint("review_capacity_per_day > 0", name='chk_expertise_capacity'),
        sa.CheckConstraint("active_reviews_count >= 0", name='chk_expertise_active_count'),
    )
    op.create_index('idx_team_expertise_routing', 'team_expertise', ['team_id', 'experience_level', 'active_reviews_count'])
    op.create_index('idx_team_languages_gin', 'team_expertise', ['primary_languages'], postgresql_using='gin')
    op.create_index('idx_team_domains_gin', 'team_expertise', ['domains'], postgresql_using='gin')

    # 10. Table: knowledge_base
    op.create_table(
        'knowledge_base',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('pattern_key', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('problem_statement', sa.Text(), nullable=False),
        sa.Column('solution_pattern', sa.Text(), nullable=False),
        sa.Column('code_example_bad', sa.Text(), nullable=True),
        sa.Column('code_example_good', sa.Text(), nullable=True),
        sa.Column('applicable_languages', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rating_positive', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rating_negative', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pattern_key', name='uq_pattern_key'),
        sa.CheckConstraint("usage_count >= 0", name='chk_kb_usage_count'),
        sa.CheckConstraint("rating_positive >= 0", name='chk_kb_rating_pos'),
        sa.CheckConstraint("rating_negative >= 0", name='chk_kb_rating_neg'),
    )
    op.create_index('idx_kb_category_pattern', 'knowledge_base', ['category', 'pattern_key'])
    op.create_index('idx_kb_tags_gin', 'knowledge_base', ['tags'], postgresql_using='gin')
    op.execute("CREATE INDEX idx_kb_fts ON knowledge_base USING GIN (to_tsvector('english', title || ' ' || problem_statement || ' ' || solution_pattern))")

    # 11. Table: metrics_history
    op.create_table(
        'metrics_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('repo_owner', sa.String(length=255), nullable=False),
        sa.Column('repo_name', sa.String(length=255), nullable=False),
        sa.Column('measurement_date', sa.Date(), nullable=False),
        sa.Column('total_reviews_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('avg_overall_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('avg_security_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('avg_test_coverage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('avg_processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('technical_debt_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('critical_findings_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('high_findings_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cache_hit_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('cost_savings_total_usd', sa.Numeric(precision=12, scale=2), server_default='0.00', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repo_owner', 'repo_name', 'measurement_date', name='uq_repo_measurement_date'),
        sa.CheckConstraint("total_reviews_count >= 0", name='chk_metrics_total_reviews'),
        sa.CheckConstraint("avg_overall_score IS NULL OR (avg_overall_score >= 0.0 AND avg_overall_score <= 100.0)", name='chk_metrics_overall_score'),
        sa.CheckConstraint("avg_security_score IS NULL OR (avg_security_score >= 0.0 AND avg_security_score <= 100.0)", name='chk_metrics_security_score'),
        sa.CheckConstraint("avg_test_coverage IS NULL OR (avg_test_coverage >= 0.0 AND avg_test_coverage <= 100.0)", name='chk_metrics_coverage'),
        sa.CheckConstraint("technical_debt_score IS NULL OR (technical_debt_score >= 0.0 AND technical_debt_score <= 100.0)", name='chk_metrics_debt_score'),
        sa.CheckConstraint("critical_findings_count >= 0", name='chk_metrics_crit_count'),
        sa.CheckConstraint("high_findings_count >= 0", name='chk_metrics_high_count'),
        sa.CheckConstraint("cache_hit_rate IS NULL OR (cache_hit_rate >= 0.0 AND cache_hit_rate <= 100.0)", name='chk_metrics_cache_hit'),
        sa.CheckConstraint("cost_savings_total_usd >= 0.0", name='chk_metrics_cost_savings'),
    )
    op.create_index('idx_metrics_repo_date', 'metrics_history', ['repo_owner', 'repo_name', sa.text('measurement_date DESC')])

    # Auxiliary 1: api_keys
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('key_hash', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('scopes', sa.String(length=255), server_default='review:read,review:write', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash', name='uq_api_key_hash')
    )

    # Auxiliary 2: custom_rules
    op.create_table(
        'custom_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=50), server_default='all', nullable=False),
        sa.Column('pattern', sa.Text(), nullable=False),
        sa.Column('rule_type', sa.String(length=30), server_default='ast_pattern', nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('remediation_template', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_custom_rule_name'),
        sa.CheckConstraint("rule_type IN ('ast_pattern', 'regex', 'semgrep_yaml')", name='chk_custom_rule_type'),
        sa.CheckConstraint("severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')", name='chk_custom_rule_severity'),
    )
    op.create_index('idx_custom_rules_lang_active', 'custom_rules', ['language', 'is_active'])

    # Auxiliary 3: review_feedback
    op.create_table(
        'review_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('is_helpful', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('false_positives', sa.Integer(), server_default='0', nullable=False),
        sa.Column('false_negatives', sa.Integer(), server_default='0', nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('review_id', name='uq_review_feedback_review_id'),
        sa.CheckConstraint('rating BETWEEN 1 AND 5', name='chk_feedback_rating'),
        sa.CheckConstraint('false_positives >= 0', name='chk_feedback_fp'),
        sa.CheckConstraint('false_negatives >= 0', name='chk_feedback_fn'),
    )


def downgrade() -> None:
    # Drop in reverse topological order
    op.drop_table('review_feedback')
    op.drop_table('custom_rules')
    op.drop_table('api_keys')
    op.drop_table('metrics_history')
    op.drop_table('knowledge_base')
    op.drop_table('team_expertise')
    op.drop_table('ml_predictions')
    op.drop_table('accessibility_reports')
    op.drop_table('cost_analysis')
    op.drop_table('compliance_results')
    op.drop_table('testing_findings')
    op.drop_table('performance_findings')
    op.drop_table('security_findings')
    op.drop_table('reviews')
```

---

## 7. Disaster Recovery, Continuous Archiving & Backup Runbooks

Enterprise production requirements dictate a Recovery Point Objective (RPO) $\le 5$ minutes and a Recovery Time Objective (RTO) $\le 30$ minutes.

### Continuous WAL Archiving Configuration

Continuous Write-Ahead Log (WAL) archiving captures every transaction delta between physical base backups.

```ini
# File: /etc/postgresql/16/main/postgresql.conf
# WAL Archiving and Replication Parameters
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /mnt/wal_archive/%f.gz && gzip < %p > /mnt/wal_archive/%f.gz'
archive_timeout = 300                 # Force rotation every 5 minutes to guarantee 5-minute RPO
max_wal_senders = 10
wal_keep_size = 16384MB               # Retain 16GB WAL on primary to support replication lags
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
```

### Physical Base Backup Runbook

Executes daily at 02:00 UTC via cron to produce byte-identical, compressed binary base backups.

```bash
#!/usr/bin/env bash
# File: scripts/db/daily_basebackup.sh
# Production Physical Database Backup Script
set -euo pipefail

BACKUP_ROOT="/mnt/backups/postgresql/base"
DATE=$(date +%Y%m%d_%H%M%S)
TARGET_DIR="${BACKUP_ROOT}/${DATE}"
LOG_FILE="/var/log/postgresql/basebackup.log"

mkdir -p "${TARGET_DIR}"
echo "[$(date -u)] Starting physical pg_basebackup to ${TARGET_DIR}..." | tee -a "${LOG_FILE}"

# Execute low-impact streaming base backup with transaction logs included (-Xs)
pg_basebackup \
  -h localhost \
  -p 5432 \
  -U replicator \
  -D "${TARGET_DIR}" \
  -Fp \
  -Xs \
  -P \
  -c fast \
  -R \
  2>&1 | tee -a "${LOG_FILE}"

echo "[$(date -u)] Compressing basebackup directory..." | tee -a "${LOG_FILE}"
tar -czf "${TARGET_DIR}.tar.gz" -C "${TARGET_DIR}" .
rm -rf "${TARGET_DIR}"

# Compute SHA256 checksum for audit and backup verification
sha256sum "${TARGET_DIR}.tar.gz" > "${TARGET_DIR}.tar.gz.sha256"

# Retain base backups for 30 days
find "${BACKUP_ROOT}" -name "*.tar.gz*" -mtime +30 -delete

echo "[$(date -u)] Basebackup successfully completed: ${TARGET_DIR}.tar.gz" | tee -a "${LOG_FILE}"
```

### Multi-Threaded Logical Backup Runbook

Executes hourly to export portable, table-level snapshots in parallel directory format.

```bash
#!/usr/bin/env bash
# File: scripts/db/hourly_pgdump.sh
# Production Parallel Directory Logical Backup
set -euo pipefail

BACKUP_DIR="/mnt/backups/postgresql/logical"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_PATH="${BACKUP_DIR}/cerberus_dump_${TIMESTAMP}"
LOG_FILE="/var/log/postgresql/logical_dump.log"

mkdir -p "${BACKUP_DIR}"
echo "[$(date -u)] Starting multi-threaded pg_dump (-j 4) to ${DUMP_PATH}..." | tee -a "${LOG_FILE}"

# Directory-format parallel dump (-Fd -j 4)
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
  -h localhost \
  -p 5432 \
  -U cerberus \
  -d cerberus_db \
  -Fd \
  -j 4 \
  -f "${DUMP_PATH}" \
  2>&1 | tee -a "${LOG_FILE}"

# Retain hourly snapshots for 7 days
find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +

echo "[$(date -u)] Logical backup complete: ${DUMP_PATH}" | tee -a "${LOG_FILE}"
```

### Step-by-Step Point-in-Time Recovery (PITR) Runbook

In the event of an unrecoverable crash, human error (e.g. accidental `DROP TABLE`), or data corruption at timestamp `TARGET_TIME="2026-09-24 14:15:00 UTC"`, execute this 8-step disaster recovery runbook.

```bash
# File: docs/runbooks/pitr_recovery.sh
# Emergency Point-in-Time Recovery (PITR) Runbook

# STEP 1: Immediately isolate the cluster and stop PostgreSQL to prevent write pollution
sudo systemctl stop postgresql

# STEP 2: Move the damaged cluster data directory aside for post-incident forensic analysis
sudo mv /var/lib/postgresql/16/main /var/lib/postgresql/16/main_corrupted_$(date +%s)

# STEP 3: Recreate clean data directory with strict ownership and permission boundaries
sudo mkdir -p /var/lib/postgresql/16/main
sudo chown -R postgres:postgres /var/lib/postgresql/16/main
sudo chmod 700 /var/lib/postgresql/16/main

# STEP 4: Extract the latest valid physical base backup prior to the target corruption timestamp
# Example: Using 20260924_020000 base backup
sudo -u postgres tar -xzf /mnt/backups/postgresql/base/20260924_020000.tar.gz -C /var/lib/postgresql/16/main

# STEP 5: Create the recovery signal file to inform the engine to enter standby recovery
sudo -u postgres touch /var/lib/postgresql/16/main/recovery.signal

# STEP 6: Configure recovery parameters inside postgresql.auto.conf
sudo -u postgres tee -a /var/lib/postgresql/16/main/postgresql.auto.conf > /dev/null <<'EOF'
# Point-In-Time Recovery Configuration
restore_command = 'gunzip < /mnt/wal_archive/%f.gz > %p'
recovery_target_time = '2026-09-24 14:15:00 UTC'
recovery_target_action = 'promote'
EOF

# STEP 7: Start the PostgreSQL engine in recovery mode
sudo systemctl start postgresql

# STEP 8: Tail engine log and verify timeline promotion and recovery completion
sudo tail -f /var/log/postgresql/postgresql-16-main.log | grep -E "restored log file|recovery target reached|database system is ready to accept read-write connections"
```

---

## 8. Redis Distributed Caching Architecture & Keyspace Strategy

The architecture employs **Redis 7+** as an in-memory cache and atomic token bucket rate limiter to offload read pressure from PostgreSQL and guarantee instant deduplication of identical code submissions.

### Keyspace Taxonomy & Key Hierarchy

All Redis keys are strictly namespaced under the `cvai:` prefix:

```text
# File: docs/diagrams/redis_keyspace.txt
cvai:
 ├── cache:
 │    └── {sha256_code_digest}       -> STRING (Serialized orjson CodeReviewResponse), TTL: 604,800s (7 days)
 ├── ratelimit:
 │    └── {api_key_hash}             -> ZSET (Member: unique req_uuid, Score: epoch ms timestamp), TTL: 3,600s
 ├── review:
 │    ├── status:{review_id}         -> STRING ("queued" | "processing" | "completed" | "failed"), TTL: 3,600s
 │    └── lock:{review_id}           -> STRING (Worker hostname mutex), TTL: 300s (5 min)
 ├── analytics:
 │    └── {owner}:{repo}:{date}      -> STRING (JSON aggregate KPIs), TTL: 900s (15 min)
 └── team:
      └── {team_id}:active           -> SET (Member IDs available for routing), TTL: 600s (10 min)
```

### High-Performance Serialization & Deduplication

Payloads are serialized using `orjson` (up to 10x faster than standard library `json`), with deterministic key sorting and UTF-8 byte representation.

```python
# File: src/core/caching.py
"""Redis Distributed Caching Engine with SHA-256 Fingerprinting."""
import hashlib
from typing import Optional, Dict, Any
import orjson
import redis.asyncio as aioredis
from src.config import settings

redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=False)


def compute_code_hash(code: str, language: str, rules_version: int = 1) -> str:
    """Generate deterministic SHA-256 fingerprint for code snippet caching."""
    normalized = "\n".join([line.rstrip() for line in code.strip().splitlines() if line.strip()])
    payload = f"v{rules_version}:{language.lower()}:{normalized}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def get_cached_review(code_hash: str) -> Optional[Dict[str, Any]]:
    """Retrieve serialized review from Redis."""
    key = f"cvai:cache:{code_hash}".encode("utf-8")
    raw = await redis_client.get(key)
    if raw:
        data = orjson.loads(raw)
        data["cache_hit"] = True
        return data
    return None


async def set_cached_review(code_hash: str, review_data: Dict[str, Any]) -> None:
    """Store serialized review in Redis with 7-day TTL."""
    key = f"cvai:cache:{code_hash}".encode("utf-8")
    # orjson serializes dataclasses, UUIDs, and datetimes natively
    serialized = orjson.dumps(review_data, option=orjson.OPT_SORT_KEYS)
    await redis_client.set(key, serialized, ex=settings.CACHE_TTL_SECONDS)
```

### Time-to-Live (TTL) Policy Matrix

| Key Pattern | Data Structure | TTL | Eviction Policy | Rationale |
|-------------|----------------|-----|-----------------|-----------|
| `cvai:cache:{sha256}` | String (orjson) | 604,800s (7 Days) | `volatile-lru` | Code reviews for identical snippets remain valid across active sprint cycles. |
| `cvai:ratelimit:{hash}` | Sorted Set (ZSET) | 3,600s (1 Hour) | `volatile-ttl` | Rolling 1-hour sliding-window request timestamps. |
| `cvai:review:status:{id}` | String | 3,600s (1 Hour) | `volatile-lru` | Polling state during and immediately following review completion. |
| `cvai:review:lock:{id}` | String (Mutex) | 300s (5 Min) | `volatile-ttl` | Prevents redundant worker concurrency during multi-agent orchestration. |
| `cvai:analytics:{repo}:{date}` | String (JSON) | 900s (15 Min) | `volatile-lru` | Frequent dashboard reads without querying relational aggregation tables. |
| `cvai:team:{id}:active` | Set | 600s (10 Min) | `volatile-lru` | Active team reviewer availability status. |

### Cache Invalidation & Consistency Matrix

| Event Trigger | Target Keyspace | Invalidation Action | Fallback Strategy |
|---------------|-----------------|---------------------|-------------------|
| **Git Commit Pushed** | `cvai:cache:{sha256}` | Natural cache miss via altered code SHA-256 fingerprint. | Old commit results expire naturally via 7-day TTL. |
| **Review State Update** | `cvai:review:status:{id}` | Direct atomic overwrite: `SET cvai:review:status:{id} "completed" EX 3600`. | Read-through fallback to PostgreSQL `reviews` table. |
| **Custom Rule Registered** | `cvai:cache:*` | Rules version increment: increments global version counter prepended to code hash. | Instant cache invalidation without requiring expensive `KEYS` or `SCAN` operations. |
| **Team Member Updated** | `cvai:team:{team_id}:active`| Explicit key deletion: `DEL cvai:team:{team_id}:active`. | Re-queried from PostgreSQL `team_expertise` table on next routing evaluation. |
| **API Key Revoked** | `cvai:ratelimit:{hash}` | Key deletion: `DEL cvai:ratelimit:{hash}`. | Relational DB lookup in `api_keys` returns 401 Unauthorized immediately. |

---

## 9. Enterprise High-Concurrency Connection Pooling Strategy

To support over 1,000 concurrent developer submissions without exhausting PostgreSQL process memory, a dual-layer pooling strategy is implemented: client-side `asyncpg` engine pooling inside the FastAPI process, fronted by an enterprise `PgBouncer` transaction-pooling cluster.

```text
# File: docs/diagrams/connection_pooling.txt
┌────────────────────────────────────────────────────────┐
│             FastAPI Application Instances              │
│  (asyncpg Engine Pool: pool_size=25, max_overflow=15)  │
└───────────────────────────┬────────────────────────────┘
                            │ (Up to 1,000 Client Conns)
                            ▼
┌────────────────────────────────────────────────────────┐
│                 Enterprise PgBouncer                   │
│       (pool_mode = transaction, max_client_conn=1000)  │
└───────────────────────────┬────────────────────────────┘
                            │ (40-60 Persistent Server Conns)
                            ▼
┌────────────────────────────────────────────────────────┐
│               PostgreSQL 16 Database Cluster           │
│              (max_connections = 100)                   │
└────────────────────────────────────────────────────────┘
```

### Client-Side `asyncpg` Engine Configuration

```python
# File: src/db/session.py
"""SQLAlchemy 2.0 Asynchronous Database Session Management with asyncpg."""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    async_sessionmaker, 
    AsyncSession
)
from src.config import settings

# Enterprise asyncpg engine tuned for high concurrency and connection recycling
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=25,             # Persistent active connections allocated per API worker
    max_overflow=15,          # Temporary burst connections permitted under peak traffic
    pool_timeout=30.0,        # Seconds to wait for an available pool slot before raising 503
    pool_recycle=1800,        # Reconnect every 30 minutes to clean up stale socket descriptors
    pool_pre_ping=True,       # Health probe before loaning a connection to the application
    echo=False,
    connect_args={
        "command_timeout": 60,
        "server_settings": {
            "application_name": "cerberus_api_worker",
            "statement_timeout": "30000",                # Enforce 30-second query execution limit
            "idle_in_transaction_session_timeout": "10000"  # Terminate uncommitted tx after 10s
        }
    }
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding request-scoped asynchronous database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Startup initialization probe confirming database connectivity."""
    async with engine.begin() as conn:
        await conn.execute(sa.text("SELECT 1"))


async def close_db() -> None:
    """Graceful teardown disposing active connection pools on shutdown."""
    await engine.dispose()
```

### Enterprise PgBouncer Configuration

PgBouncer operates in **transaction pooling** mode, multiplexing 1,000 active client connections into 40–60 persistent server connections on PostgreSQL.

```ini
; File: /etc/pgbouncer/pgbouncer.ini
[databases]
cerberus_db = host=postgres-primary.internal port=5432 dbname=cerberus_db pool_size=50

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

; Transaction pooling mode provides maximum client scaling
pool_mode = transaction

; Connection limits
max_client_conn = 1000
default_pool_size = 40
min_pool_size = 10
reserve_pool_size = 10
reserve_pool_timeout = 5.0
max_db_connections = 60

; Timeouts and Socket Protection
server_idle_timeout = 60.0
server_connect_timeout = 15.0
server_login_retry = 15.0
client_idle_timeout = 120.0
client_login_timeout = 30.0
query_timeout = 60.0

; Logging and Instrumentation
log_connections = 1
log_disconnections = 1
log_pooler_errors = 1
stats_period = 60
```

---

## 10. Diagnostic Database Monitoring & Observability Queries

To maintain high availability, database administrators and SREs use these diagnostic queries for real-time observability.

### Query 1: Top 10 Slowest Executing Queries

Identifies latency outliers and query plans requiring optimization using `pg_stat_statements`.

```sql
-- # File: scripts/db/diagnostics/slow_queries.sql
-- Top 10 Slowest Executing Queries
SELECT 
    round(total_exec_time::numeric, 2) AS total_time_ms,
    calls,
    round(mean_exec_time::numeric, 2) AS mean_time_ms,
    round(stddev_exec_time::numeric, 2) AS stddev_time_ms,
    round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 2) AS percentage_overall,
    query
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Query 2: Index Hit Ratio Analysis

Measures how often queries utilize indexes rather than sequential full-table scans. Alert if ratio is below 99.00%.

```sql
-- # File: scripts/db/diagnostics/index_hit_ratio.sql
-- Index Hit Ratio per Table (Target > 99.0%)
SELECT 
    relname AS table_name,
    idx_scan AS index_scans,
    seq_scan AS sequential_scans,
    round(100.0 * idx_scan / nullif(idx_scan + seq_scan, 0), 2) AS index_hit_percentage
FROM pg_stat_user_tables
WHERE (idx_scan + seq_scan) > 100
ORDER BY index_hit_percentage ASC;
```

### Query 3: Buffer Cache Hit Ratio Analysis

Measures memory caching efficiency in shared buffers. Alert if ratio is below 99.00%.

```sql
-- # File: scripts/db/diagnostics/cache_hit_ratio.sql
-- Overall Buffer Cache Hit Ratio (Target > 99.0%)
SELECT 
    sum(heap_blks_read) AS heap_blocks_read_from_disk,
    sum(heap_blks_hit) AS heap_blocks_hit_in_cache,
    round((sum(heap_blks_hit) * 100.0 / nullif(sum(heap_blks_hit) + sum(heap_blks_read), 0)), 3) AS cache_hit_ratio_pct
FROM pg_statio_user_tables;
```

### Query 4: Dead Tuples, Table Bloat & Vacuum Optimization

Monitors dead tuple buildup to verify autovacuum efficiency and detect table bloat.

```sql
-- # File: scripts/db/diagnostics/table_bloat.sql
-- Dead Tuples and Autovacuum Tracking
SELECT 
    relname AS table_name,
    n_live_tup AS live_tuples,
    n_dead_tup AS dead_tuples,
    round(100.0 * n_dead_tup / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_tuple_ratio_pct,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY dead_tuples DESC;
```

### Query 5: Active & Idle Connection State Analysis

Inspects connection allocation across application workers and isolates connection leaks.

```sql
-- # File: scripts/db/diagnostics/connection_states.sql
-- Active and Idle Connections by State
SELECT 
    COALESCE(application_name, '[unknown]') AS app_name,
    state,
    count(*) AS connection_count,
    max(now() - state_change) AS max_duration_in_state,
    max(now() - xact_start) AS max_transaction_age
FROM pg_stat_activity
WHERE datname = 'cerberus_db'
GROUP BY application_name, state
ORDER BY connection_count DESC;
```

### Query 6: Lock Contention & Transaction Blocking Analysis

Identifies blocked transactions and locking root queries during contention incidents.

```sql
-- # File: scripts/db/diagnostics/lock_contention.sql
-- Blocked Queries and Lock Contention Resolution
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS blocking_statement,
    now() - blocked_activity.query_start AS waiting_duration
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

---

## 11. Summary & Next Document Pointer

### Architectural Summary
The Cerberus database design provides:
- **Comprehensive DDL & Data Integrity**: 50+ executable SQL statements across 11 core domain tables and 3 auxiliary tables with strict `ON DELETE CASCADE` cascades, check constraints, and microsecond-precision audit triggers.
- **Enterprise High-Throughput Indexing**: Multi-column composite B-trees, GIN indexing for JSONB telemetry and text arrays, and GiST/tsvector inverted full-text search indexing.
- **Automated Asynchronous Schema Migrations**: Fully configured Alembic migration environment utilizing `asyncpg` with `NullPool` for clean zero-downtime schema evolution.
- **Zero Data Loss Resilience**: Continuous WAL archiving, daily physical streaming backups, hourly multi-threaded directory dumps, and a concrete 8-step PITR recovery runbook ensuring 5-minute RPO and 30-minute RTO.
- **High-Performance Distributed Caching & Pooling**: Sub-millisecond fingerprint caching in Redis via `orjson`, sliding-window rate limiting, client-side connection pooling, and PgBouncer transaction pooling scaling to 1,000 client connections.

### Pointer to Next Document
The persistence layer documented here directly backs the application interfaces and routing contracts detailed in the next document:

👉 **[API Specifications & FastAPI Setup (`API_SPECIFICATIONS.md`)](./API_SPECIFICATIONS.md)**
*(Covers OpenAPI 3.1 YAML specifications, OAuth2 authentication, sliding-window rate limiters, RFC 7807 problem details error handling, and production-grade modular FastAPI router code).*
