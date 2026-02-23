# Agents Reference - 에이전트 시스템 Agent Catalog

Purpose: Complete reference catalog of 에이전트 시스템's 26 specialized agents with `{domain}-{role}` naming convention and 7-tier hierarchy.

Last Updated: 2025-11-25
Version: 2.0.0

---

## Quick Reference (30 seconds)

오케스트레이터가 위임 ALL tasks to specialized agents. 26 agents organized in 7 tiers:

Tier 1: `workflow-*` (Command Processors) - Always Active
Tier 2: `core-*` (Orchestration & Quality) - Auto-triggered
Tier 3: `{domain}-*` (Domain Experts) - Lazy-loaded
Tier 4: `mcp-*` (MCP Integrators) - Resume-enabled
Tier 5: `factory-*` (Factory Agents) - Meta-development
Tier 6: `support-*` (Support Services) - On-demand
Tier 7: `ai-*` (AI & Specialized) - Specialized tasks

Agent Selection:
- Simple (1 file): 1-2 agents sequential
- Medium (3-5 files): 2-3 agents sequential
- Complex (10+ files): 5+ agents parallel/sequential

All agents use Task() delegation:
```python
result = Task(subagent_type="code-backend", prompt="...", context={...})
```

---

## Implementation Guide (5 minutes)

### Naming Convention: `{domain}-{role}`

All 에이전트 시스템 agents follow consistent naming:

| Domain | Purpose | Examples |
|--------|---------|----------|
| `workflow` | Core workflow command processors | workflow-spec, workflow-ddd |
| `core` | Orchestration & quality management | core-planner, core-quality |
| `code` | Code implementation experts | code-backend, code-frontend |
| `data` | Data-related experts | data-database |
| `infra` | Infrastructure/DevOps experts | infra-devops |
| `design` | Design/UX experts | design-uiux |
| `security` | Security experts | security-expert |
| `mcp` | MCP server integrations | mcp-context7, mcp-sequential-thinking |
| `factory` | Meta-generation agents | factory-agent, factory-skill |
| `support` | Support services | support-debug, support-claude |
| `ai` | AI model integrations | ai-codex, ai-gemini |

---

### Tier 1: Command Processors (Essential - Always Active)

Core command processors directly bound to 시스템 명령어.

| Agent | Command | Purpose |
|-------|---------|---------|
| `workflow-project` | `/project` | Project initialization and setup |
| `workflow-spec` | `/plan` | EARS SPEC generation and planning |
| `workflow-ddd` | `/run` | DDD ANALYZE-PRESERVE-IMPROVE execution |
| `workflow-docs` | `/sync` | Documentation generation and synchronization |

Loading: Always active (loaded on command invocation)

---

### Tier 2: Orchestration & Quality (Auto-triggered)

Orchestration and quality management agents.

| Agent | Trigger | Purpose |
|-------|---------|---------|
| `core-planner` | `/run` Phase 1 | SPEC analysis and execution strategy |
| `core-quality` | Post-implementation | TRUST 5 validation |
| `core-git` | Git operations | Branch, commit, and PR management |

Loading: Auto-triggered based on workflow phase

---

### Tier 3: Domain Experts (Lazy-loaded)

Domain-specific implementation experts.

| Agent | Domain | Purpose |
|-------|--------|---------|
| `code-backend` | Backend | Backend architecture and API design |
| `code-frontend` | Frontend | Frontend UI/UX implementation |
| `data-database` | Data | Database schema design and migration |
| `infra-devops` | Infrastructure | DevOps, monitoring, and performance |
| `security-expert` | Security | Security analysis and OWASP validation |
| `design-uiux` | Design | UI/UX, components, and accessibility |

Loading: Lazy-loaded based on keyword detection or SPEC requirements

Trigger Keywords:
- `code-backend`: "backend", "api", "server", "endpoint"
- `code-frontend`: "frontend", "ui", "component", "page"
- `data-database`: "database", "schema", "migration", "query"
- `infra-devops`: "deploy", "ci/cd", "performance", "monitoring"
- `security-expert`: "security", "auth", "encryption", "owasp"
- `design-uiux`: "design", "ux", "accessibility", "component"

---

### Tier 4: MCP Integrators (Resume-enabled)

External MCP server integrations with context continuity support.

| Agent | MCP Server | Purpose |
|-------|------------|---------|
| `mcp-context7` | Context7 | Documentation research and API reference |
| `mcp-pencil` | Pencil | Design system integration |
| `mcp-notion` | Notion | Knowledge base integration |
| `mcp-playwright` | Playwright | Browser automation and E2E testing |
| `mcp-sequential-thinking` | Sequential-Thinking | Complex reasoning and strategic analysis |

Resume Pattern (40-60% token savings):
```python
# Initial call
result = Task(subagent_type="mcp-context7", prompt="Research React 19 APIs")
agent_id = result.agent_id

# Resume with context
result2 = Task(subagent_type="mcp-context7", prompt="Compare with React 18", resume=agent_id)
```

Benefits:
- Token savings: 40-60% reduction vs. fresh context
- Context accuracy: 95%+ in resumed sessions
- Multi-day analysis: Support for long-running tasks

---

### Tier 5: Factory Agents (Meta-development)

Meta-generation agents for 에이전트 시스템 development.

| Agent | Purpose |
|-------|---------|
| `factory-agent` | New agent creation and configuration |
| `factory-skill` | Skill definition creation and management |
| `factory-command` | Custom slash command creation and optimization |

Use Case: When developing 에이전트 시스템 itself (not for end-user projects)

---

### Tier 6: Support (On-demand)

Support and utility services.

| Agent | Purpose |
|-------|---------|
| `support-debug` | Error analysis and diagnostic support |
| `support-claude` | Claude Code configuration management |

Loading: On-demand when errors occur or configuration changes needed

---

### Tier 7: AI & Specialized

AI model integrations and specialized services.

| Agent | Purpose |
|-------|---------|
| `ai-codex` | OpenAI Codex CLI integration |
| `ai-gemini` | Google Gemini API integration |
| `ai-banana` | Gemini 3 image generation |

Loading: On-demand when AI model integration required

---

### System Agents

Built-in system agents for codebase exploration.

| Agent | Purpose |
|-------|---------|
| `Explore` | Codebase exploration and file system analysis |
| `Plan` | Strategic decomposition and planning |

Note: These are Claude Code built-in agents, not 에이전트 시스템 custom agents.

---

## Advanced Implementation (10+ minutes)

### Agent Selection Criteria

| Task Complexity | Files | Architecture Impact | Agents | Strategy |
|----------------|-------|---------------------|--------|----------|
| Simple | 1 file | No impact | 1-2 agents | Sequential |
| Medium | 3-5 files | Moderate | 2-3 agents | Sequential |
| Complex | 10+ files | High impact | 5+ agents | Mixed parallel/sequential |

Decision Tree:
```
Is this a new feature or architecture change?
 YES, 10+ files → Complex (5+ agents, parallel/sequential)
 YES, 3-5 files → Medium (2-3 agents, sequential)
 NO, 1-2 files → Simple (1-2 agents, sequential)
```

---

### Delegation Principles

1. Agent-First: 오케스트레이터는 태스크를 직접 실행하지 않음. ALWAYS delegates via Task()

2. Naming Consistency: All agents follow `{domain}-{role}` pattern
 - Lowercase only
 - Hyphen separator
 - Domain prefix indicates tier

3. Context Passing: Pass each agent's results as context to the next agent
 ```python
 result1 = Task("code-backend", "Design API")
 result2 = Task("code-frontend", "Implement UI", context={"api_design": result1})
 ```

4. Sequential vs Parallel:
 - Sequential: When dependencies exist between agents
 - Parallel: When agents work independently

---

### Merged Agents (Historical Reference)

The following agents were merged to reduce complexity:

| Old Agent | Merged Into | Reason |
|-----------|-------------|--------|
| doc-syncer | workflow-docs | Documentation consolidation |
| trust-checker | core-quality | Quality gate unification |
| api-designer | code-backend | Backend expertise consolidation |
| migration-expert | data-database | Data operations unification |
| monitoring-expert | infra-devops | Infrastructure consolidation |
| performance-engineer | infra-devops | Infrastructure consolidation |
| component-designer | design-uiux | Design system unification |
| accessibility-expert | design-uiux | Design system unification |

Total Agents: 26 (down from 35, -26% reduction)

---

### Removed Agents

| Agent | Reason |
|-------|--------|
| format-expert | Replaced by direct linter usage (ruff, prettier) |
| sync-manager | Redundant with workflow-docs |

---

### Skill Architecture Reference

The following skills are organized for token efficiency and domain specialization:

| Category | Skills | Purpose |
|----------|--------|---------|
| Language (Separated) | lang-python, lang-typescript, lang-systems, lang-jvm, lang-mobile | Domain-specific language skills for 40-60% token savings |
| Platform (Separated) | platform-auth, platform-database, platform-deploy | Domain-specific platform skills for 30-50% token savings |
| Foundation | foundation-core, foundation-claude, foundation-context, foundation-quality | Core principles and quality gates |
| Workflow | workflow-spec, workflow-project, workflow-testing, workflow-jit-docs | Workflow automation and testing |
| Domain | domain-backend, domain-frontend, domain-database, domain-uiux | Domain expertise patterns |

Language Skills Selection Guide:

| Language Skill | Coverage | Use When |
|----------------|----------|----------|
| lang-python | Python 3.13, FastAPI, Django, pytest | Backend APIs, data science, automation |
| lang-typescript | TypeScript 5.9, React 19, Next.js 16, tRPC | Frontend, full-stack web development |
| lang-systems | Go 1.23, Rust 1.91, Fiber, Axum | Microservices, CLI tools, systems programming |
| lang-jvm | Java 21, Kotlin 2.0, Scala 3.4, Spring | Enterprise applications, big data |
| lang-mobile | Swift 6, Kotlin Android, Flutter 3.24 | iOS, Android, cross-platform mobile |

Platform Skills Selection Guide:

| Platform Skill | Providers | Use When |
|----------------|-----------|----------|
| platform-auth | Auth0, Clerk, Firebase Auth | Authentication implementation |
| platform-database | Supabase, Neon, Convex, Firestore | Database platform integration |
| platform-deploy | Vercel, Railway | Deployment and CI/CD |

Note: Agents now use specific skills based on their domain. Cross-language agents include lang-python and lang-typescript by default.

---

### Tier Loading Strategy

| Tier | Loading | Context Budget | Trigger |
|------|---------|----------------|---------|
| Tier 1 | Always active | 30% | Command invocation |
| Tier 2 | Auto-trigger | 20% | Quality gates, orchestration |
| Tier 3 | Lazy-load | 30% | Keyword detection, SPEC analysis |
| Tier 4 | On-demand | 10% | MCP operations |
| Tier 5 | On-demand | 5% | Meta-generation |
| Tier 6 | On-demand | 3% | Errors, configuration |
| Tier 7 | On-demand | 2% | AI model integration |

Total Budget: 100% of available context per workflow phase

---

### Error Handling

Common Errors:

| Error | Solution |
|-------|----------|
| "Agent not found" | Verify agent name follows `{domain}-{role}` (lowercase, hyphenated) |
| "Agent not responding" | Check agent permissions in settings.json |
| "Context overflow" | Execute /clear and retry with smaller context |
| "Permission denied" | Update IAM rules in .claude/settings.json |

Error Recovery Pattern:
```python
try:
 result = Task("code-backend", "Implement feature")
except AgentNotFoundError:
 # Check agent name format
 result = Task("code-backend", "Implement feature") # Corrected name
except PermissionError:
 # Update settings.json IAM rules
 result = Task("code-backend", "Implement feature", permissions=["write"])
```

---

## Works Well With

Skills:
- [foundation-core](../SKILL.md) - Parent skill (this module is part of it)
- [foundation-context](../../foundation-context/SKILL.md) - Token budget and session state
- [foundation-claude](../../foundation-claude/SKILL.md) - Claude Code configuration

Other Modules:
- [delegation-patterns.md](delegation-patterns.md) - Delegation strategies
- [token-optimization.md](token-optimization.md) - Token budget management
- [execution-rules.md](execution-rules.md) - Security and permissions

Commands:
- `/project` → `workflow-project`
- `/plan` → `workflow-spec`
- `/run` → `workflow-ddd`
- `/sync` → `workflow-docs`

---

Total Agents: 26 active agents (down from 35, -26% reduction)
Maintained by: 에이전트 시스템 Team
Status: Production Ready
