# Commands Reference - 에이전트 시스템 Core Commands

Purpose: Complete reference for 에이전트 시스템's 6 core commands used in SPEC-First DDD workflow.

Last Updated: 2025-11-25
Version: 2.0.0

---

## Quick Reference (30 seconds)

에이전트 시스템 provides 6 core commands for SPEC-First DDD execution:

| Command            | Purpose                | Phase         |
| ------------------ | ---------------------- | ------------- |
| `/project`  | Project initialization | Setup         |
| `/plan`     | SPEC generation        | Planning      |
| `/run`      | DDD implementation     | Development   |
| `/sync`     | Documentation sync     | Documentation |
| `/feedback` | Feedback collection    | Improvement   |
| `/99-release` | Production deployment  | Release       |

Required Workflow:
```
1. /project # Initialize
2. /plan "description" # Generate SPEC
3. /clear # Clear context (REQUIRED)
4. /run SPEC-001 # Implement
5. /sync SPEC-001 # Document
6. /feedback # Improve
```

Critical Rule: Execute `/clear` after `/plan` (saves 45-50K tokens)

---

## Implementation Guide (5 minutes)

### `/project` - Project Initialization

Purpose: Initialize project structure and generate configuration

Agent Delegation: `workflow-project`

Usage:
```bash
/project
/project --with-git
```

What It Does:
1. Creates `.sudapapa/` directory structure
2. Generates `config.json` with default settings
3. Initializes Git repository (if `--with-git` flag provided)
4. Sets up 에이전트 시스템 workflows

Output:
- `.sudapapa/` directory
- `.sudapapa/config/config.yaml`
- `.sudapapa/memory/` (empty, ready for session state)
- `.sudapapa/logs/` (empty, ready for logging)

Next Step: Ready for SPEC generation via `/plan`

Example:
```
User: /project
시스템: 프로젝트 초기화 완료.
 - .sudapapa/config/config.yaml created
 - Git workflow set to 'manual' mode
 Ready for SPEC generation.
```

---

### `/plan` - SPEC Generation

Purpose: Generate SPEC document in EARS format

Agent Delegation: `workflow-spec`

Usage:
```bash
/plan "Implement user authentication endpoint (JWT)"
/plan "Add dark mode toggle to settings page"
```

What It Does:
1. Analyzes user request
2. Generates EARS format SPEC document
3. Creates `.sudapapa/specs/SPEC-XXX/` directory
4. Saves `spec.md` with requirements

EARS Format (5 sections):
- WHEN (trigger conditions)
- IF (preconditions)
- THE SYSTEM SHALL (functional requirements)
- WHERE (constraints)
- UBIQUITOUS (quality requirements)

Output:
- `.sudapapa/specs/SPEC-001/spec.md` (EARS document)
- SPEC ID assigned (auto-incremented)

CRITICAL: Execute `/clear` immediately after completion
- Saves 45-50K tokens
- Prepares clean context for implementation

Example:
```
User: /plan "Implement user authentication endpoint (JWT)"
시스템: SPEC-001 생성 완료.
 Location: .sudapapa/specs/SPEC-001/spec.md

 IMPORTANT: Execute /clear now to free 45-50K tokens.
```

---

### `/run` - DDD Implementation

Purpose: Execute ANALYZE-PRESERVE-IMPROVE cycle

Agent Delegation: `workflow-ddd`

Usage:
```bash
/run SPEC-001
/run SPEC-002
```

What It Does:
1. Reads SPEC document
2. Executes DDD cycle in 3 phases:
 - ANALYZE: Understand requirements and existing behavior
 - PRESERVE: Ensure existing behavior is protected with tests
 - IMPROVE: Implement improvements incrementally
3. Validates TRUST 5 quality gates
4. Generates implementation report

DDD Process:
```
Phase 1 (ANALYZE):
 - Understand requirements from SPEC
 - Analyze existing codebase behavior
 - Identify areas of change

Phase 2 (PRESERVE):
 - Create characterization tests for existing behavior
 - Ensure all tests pass before changes
 - Run tests → ALL PASS

Phase 3 (IMPROVE):
 - Implement changes incrementally
 - Validate behavior preservation
 - Optimize code structure
 - Run tests → ALL PASS (maintained)
```

Output:
- Implemented code (in source directories)
- Test files (in test directories)
- Quality report (TRUST 5 validation)

Requirement: Test coverage ≥ 85% (TRUST 5)

Example:
```
User: /run SPEC-001
시스템: SPEC-001 DDD 구현 사이클 시작.

 ANALYZE: Requirements analyzed, 12 acceptance criteria identified
 PRESERVE: Existing behavior protected, characterization tests created
 IMPROVE: Implementation complete, all tests passing

 Test Coverage: 92% ( meets 85% threshold)
 TRUST 5: All gates passed
```

---

### `/sync` - Documentation Synchronization

Purpose: Auto-generate API documentation and project artifacts

Agent Delegation: `workflow-docs`

Usage:
```bash
/sync SPEC-001
/sync SPEC-002
```

What It Does:
1. Reads implemented code
2. Generates API documentation (OpenAPI format)
3. Creates architecture diagrams
4. Produces project completion report

Output:
- API documentation (OpenAPI/Swagger format)
- Architecture diagrams (Mermaid)
- `.sudapapa/docs/SPEC-001/` directory
- Project report

Example:
```
User: /sync SPEC-001
시스템: SPEC-001 문서 동기화 완료.

 Generated:
 - API documentation: .sudapapa/docs/SPEC-001/api.yaml
 - Architecture diagram: .sudapapa/docs/SPEC-001/architecture.md
 - Completion report: .sudapapa/docs/SPEC-001/report.md
```

---

### `/feedback` - Improvement Feedback Collection

Purpose: Error analysis and improvement suggestions

Agent Delegation: `core-quality`

Usage:
```bash
/feedback
/feedback --analyze SPEC-001
```

What It Does:
1. Analyzes errors encountered during workflow
2. Collects improvement suggestions
3. Reports to 에이전트 시스템 development team
4. Proposes error recovery strategies

Use Cases:
- Errors: When errors occur during any workflow phase
- Improvements: When 에이전트 시스템 enhancements are identified
- Analysis: Post-implementation review

Example:
```
User: /feedback
시스템: 최근 세션 피드백 수집 중.

 Errors: 2 permission issues detected
 Improvements: 1 token optimization suggestion

 Feedback submitted to 에이전트 시스템 development team.
```

---

### `/99-release` - Production Deployment

Purpose: Production deployment workflow

Agent Delegation: `infra-devops`

Usage:
```bash
/99-release
```

What It Does:
1. Validates all TRUST 5 quality gates
2. Runs full test suite
3. Builds production artifacts
4. Deploys to production environment

Note: This command is local-only and NOT synchronized to the package template. It's for local development and testing.

---

## Advanced Implementation (10+ minutes)

### Context Initialization Rules

Rule 1: Execute `/clear` AFTER `/plan` (mandatory)
- SPEC generation uses 45-50K tokens
- `/clear` frees this context for implementation phase
- Prevents context overflow

Rule 2: Execute `/clear` when context > 150K tokens
- Monitor context usage via `/context` command
- Prevents token limit exceeded errors

Rule 3: Execute `/clear` after 50+ conversation messages
- Accumulated context from conversation history
- Reset for fresh context

Why `/clear` is critical:
```
Without /clear:
 SPEC generation: 50K tokens
 Implementation: 100K tokens
 Total: 150K tokens (approaching 200K limit)

With /clear:
 SPEC generation: 50K tokens
 /clear: 0K tokens (reset)
 Implementation: 100K tokens
 Total: 100K tokens (50K budget remaining)
```

---

### Command Delegation Patterns

Each command delegates to a specific agent:

| Command            | Agent              | Agent Type              |
| ------------------ | ------------------ | ----------------------- |
| `/project`  | `workflow-project` | Tier 1 (Always Active)  |
| `/plan`     | `workflow-spec`    | Tier 1 (Always Active)  |
| `/run`      | `workflow-ddd`     | Tier 1 (Always Active)  |
| `/sync`     | `workflow-docs`    | Tier 1 (Always Active)  |
| `/feedback` | `core-quality`     | Tier 2 (Auto-triggered) |
| `/99-release` | `infra-devops`     | Tier 3 (Lazy-loaded)    |

Delegation Flow:
```
User executes command
 ↓
오케스트레이터가 명령 수신
 ↓
Command processor agent invoked
 ↓
Agent executes workflow
 ↓
Results reported to user
```

---

### Token Budget by Command

| Command        | Average Tokens | Phase Budget                          |
| -------------- | -------------- | ------------------------------------- |
| `/plan` | 45-50K         | Planning Phase (30K allocated)        |
| `/run`  | 80-100K        | Implementation Phase (180K allocated) |
| `/sync` | 20-25K         | Documentation Phase (40K allocated)   |
| Total          | 145-175K       | 250K per feature                      |

Optimization:
- Use Haiku 4.5 for `/run` (fast, cost-effective)
- Use Sonnet 4.5 for `/plan` (high-quality SPEC)
- Execute `/clear` between phases (critical)

---

### Error Handling

Common Errors:

| Error                     | Command                | Solution                                    |
| ------------------------- | ---------------------- | ------------------------------------------- |
| "Project not initialized" | `/plan`         | Run `/project` first                 |
| "SPEC not found"          | `/run SPEC-999` | Verify SPEC ID exists                       |
| "Token limit exceeded"    | Any                    | Execute `/clear` immediately                |
| "Test coverage < 85%"     | `/run`          | `core-quality` auto-generates missing tests |

Recovery Pattern:
```bash
# Error: Token limit exceeded
1. /clear # Reset context
2. /run SPEC-001 # Retry with clean context
```

---

### Workflow Variations

Standard Workflow (Full SPEC):
```
/project → /plan → /clear → /run → /sync
```

Quick Workflow (No SPEC for simple tasks):
```
/project → Direct implementation (for 1-2 file changes)
```

Iterative Workflow (Multiple SPECs):
```
/plan "Feature A" → /clear → /run SPEC-001 → /sync SPEC-001
/plan "Feature B" → /clear → /run SPEC-002 → /sync SPEC-002
```

---

### Integration with Git Workflow

Commands automatically integrate with Git based on `config.json` settings:

Manual Mode (Local Git):
- `/plan`: Prompts for branch creation
- `/run`: Auto-commits to local branch
- No auto-push

Personal Mode (GitHub Individual):
- `/plan`: Auto-creates feature branch + auto-push
- `/run`: Auto-commits + auto-push
- `/sync`: Suggests PR creation (user choice)

Team Mode (GitHub Team):
- `/plan`: Auto-creates feature branch + Draft PR
- `/run`: Auto-commits + auto-push
- `/sync`: Prepares PR for team review

---

## Works Well With

Skills:
- [foundation-core](../SKILL.md) - Parent skill
- [foundation-context](../../foundation-context/SKILL.md) - Token budget management

Other Modules:
- [spec-first-ddd.md](spec-first-ddd.md) - Detailed SPEC-First DDD process
- [token-optimization.md](token-optimization.md) - /clear execution strategies
- [agents-reference.md](agents-reference.md) - Agent catalog

Agents:
- [workflow-project](agents-reference.md#tier-1-command-processors) - `/project`
- [workflow-spec](agents-reference.md#tier-1-command-processors) - `/plan`
- [workflow-ddd](agents-reference.md#tier-1-command-processors) - `/run`
- [workflow-docs](agents-reference.md#tier-1-command-processors) - `/sync`

---

Maintained by: 에이전트 시스템 Team
Status: Production Ready
