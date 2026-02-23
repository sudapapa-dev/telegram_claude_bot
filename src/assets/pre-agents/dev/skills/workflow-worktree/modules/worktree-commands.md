# Worktree Commands Module

Purpose: Complete CLI command reference for Git worktree management with detailed usage examples and advanced options.

Version: 2.0.0
Last Updated: 2026-01-06

---

## Quick Reference (30 seconds)

Command Categories:
- Creation: new - Create isolated worktree
- Navigation: list, switch, go - Browse and navigate
- Management: sync, remove, clean - Maintain worktrees
- Status: status - Check worktree state
- Configuration: config - Manage settings

Quick Start:
1. Create worktree: worktree-cli new SPEC-001 "User Authentication"
2. Switch to worktree: worktree-cli switch SPEC-001
3. Or use shell eval: eval $(worktree-cli go SPEC-001)

---

## Creation Commands

### worktree-cli new - Create Worktree

Create a new isolated Git worktree for SPEC development.

Syntax: worktree-cli new <spec-id> [description] [options]

Arguments:
- spec-id: SPEC identifier (e.g., SPEC-001, SPEC-AUTH-001)
- description: Optional description for the worktree

Options:
- --branch <name>: Create specific branch instead of auto-generated
- --base <branch>: Base branch for new worktree (default: main)
- --template <name>: Use predefined template
- --shallow: Create shallow clone for faster setup
- --depth <number>: Clone depth for shallow clone
- --force: Force creation even if worktree exists

Examples:
- Basic creation: worktree-cli new SPEC-001 "User Auth System"
- Custom branch: worktree-cli new SPEC-002 "Payment" --branch feature/payment-gateway
- From develop: worktree-cli new SPEC-003 "API Refactor" --base develop
- With template: worktree-cli new SPEC-004 "Frontend" --template frontend
- Fast creation: worktree-cli new SPEC-005 "Bug Fixes" --shallow --depth 1

Auto-Generated Branch Pattern:
- Format: feature/SPEC-{ID}-{description-kebab-case}
- Example: SPEC-001 becomes feature/SPEC-001-user-authentication

---

## Navigation Commands

### worktree-cli list - List Worktrees

Display all registered worktrees with their status and metadata.

Syntax: worktree-cli list [options]

Options:
- --format <format>: Output format (table, json, csv)
- --status <status>: Filter by status (active, merged, stale)
- --sort <field>: Sort by field (name, created, modified, status)
- --reverse: Reverse sort order
- --verbose: Show detailed information

Examples:
- Table format: worktree-cli list
- JSON output: worktree-cli list --format json
- Active only: worktree-cli list --status active
- Sort by date: worktree-cli list --sort created
- Detailed: worktree-cli list --verbose

### worktree-cli switch - Switch to Worktree

Change current working directory to the specified worktree.

Syntax: worktree-cli switch <spec-id> [options]

Options:
- --auto-sync: Automatically sync before switching
- --force: Force switch even with uncommitted changes
- --new-terminal: Open in new terminal window

Examples:
- Basic switch: worktree-cli switch SPEC-001
- With sync: worktree-cli switch SPEC-002 --auto-sync
- Force switch: worktree-cli switch SPEC-003 --force

### worktree-cli go - Get Worktree Path

Output the cd command for shell integration.

Syntax: worktree-cli go <spec-id> [options]

Options:
- --absolute: Show absolute path
- --relative: Show relative path from current directory
- --export: Export as environment variable

Shell Integration Methods:
- eval pattern (recommended): eval $(worktree-cli go SPEC-001)
- source pattern: worktree-cli go SPEC-001 | source
- manual cd: cd $(worktree-cli go SPEC-001 --absolute)

---

## Management Commands

### worktree-cli sync - Synchronize Worktree

Synchronize worktree with its base branch.

Syntax: worktree-cli sync <spec-id> [options]

Arguments:
- spec-id: Worktree identifier (or --all for all worktrees)

Options:
- --auto-resolve: Automatically resolve simple conflicts
- --interactive: Interactive conflict resolution
- --dry-run: Show what would be synced without doing it
- --force: Force sync even with uncommitted changes
- --include <pattern>: Include only specific files
- --exclude <pattern>: Exclude specific files

Examples:
- Sync specific: worktree-cli sync SPEC-001
- Sync all: worktree-cli sync --all
- Interactive: worktree-cli sync SPEC-001 --interactive
- Preview: worktree-cli sync SPEC-001 --dry-run
- Include pattern: worktree-cli sync SPEC-001 --include "src/"
- Exclude pattern: worktree-cli sync SPEC-001 --exclude "node_modules/"

Conflict Resolution:
When conflicts detected, choose from:
1. Keep worktree version
2. Accept base branch version
3. Open merge tool
4. Skip file
5. Abort sync

### worktree-cli remove - Remove Worktree

Remove a worktree and clean up its registration.

Syntax: worktree-cli remove <spec-id> [options]

Options:
- --force: Force removal without confirmation
- --keep-branch: Keep the branch after removing worktree
- --backup: Create backup before removal
- --dry-run: Show what would be removed without doing it

Examples:
- Interactive: worktree-cli remove SPEC-001
- Force: worktree-cli remove SPEC-001 --force
- Keep branch: worktree-cli remove SPEC-001 --keep-branch
- With backup: worktree-cli remove SPEC-001 --backup
- Preview: worktree-cli remove SPEC-001 --dry-run

### worktree-cli clean - Clean Up Worktrees

Remove worktrees for merged branches or stale worktrees.

Syntax: worktree-cli clean [options]

Options:
- --merged-only: Only remove worktrees with merged branches
- --stale: Remove worktrees not updated in specified days
- --days <number>: Stale threshold in days (default: 30)
- --interactive: Interactive selection of worktrees to remove
- --dry-run: Show what would be cleaned without doing it
- --force: Skip confirmation prompts

Examples:
- Merged only: worktree-cli clean --merged-only
- Stale (30 days): worktree-cli clean --stale
- Custom threshold: worktree-cli clean --stale --days 14
- Interactive: worktree-cli clean --interactive
- Preview: worktree-cli clean --dry-run
- Force: worktree-cli clean --force

---

## Status and Configuration

### worktree-cli status - Show Worktree Status

Display detailed status information about worktrees.

Syntax: worktree-cli status [spec-id] [options]

Arguments:
- spec-id: Specific worktree (optional, shows current if not specified)

Options:
- --all: Show status of all worktrees
- --sync-check: Check if worktrees need sync
- --detailed: Show detailed Git status
- --format <format>: Output format (table, json)

Examples:
- Current worktree: worktree-cli status
- Specific worktree: worktree-cli status SPEC-001
- All with sync check: worktree-cli status --all --sync-check
- Detailed Git status: worktree-cli status SPEC-001 --detailed
- JSON output: worktree-cli status --all --format json

Status Output Includes:
- Worktree path and branch
- Commits ahead/behind base
- Modified and untracked files
- Sync status and last sync time

### worktree-cli config - Configuration Management

Manage worktree-cli configuration settings.

Syntax: worktree-cli config <action> [key] [value]

Actions:
- get [key]: Get configuration value
- set <key> <value>: Set configuration value
- list: List all configuration
- reset [key]: Reset to default value
- edit: Open configuration in editor

Configuration Keys:
- worktree_root: Root directory for worktrees
- auto_sync: Enable automatic sync (true/false)
- cleanup_merged: Auto-cleanup merged worktrees (true/false)
- default_base: Default base branch (main/develop)
- template_dir: Directory for worktree templates
- sync_strategy: Sync strategy (merge, rebase, squash)

Examples:
- List all: worktree-cli config list
- Get value: worktree-cli config get worktree_root
- Set value: worktree-cli config set auto_sync true
- Reset: worktree-cli config reset worktree_root
- Edit: worktree-cli config edit

---

## Advanced Usage

### Batch Operations

Sync all active worktrees:
- Use shell loop with list --format json and jq to extract IDs
- Run sync for each ID in sequence or parallel

Clean all merged worktrees:
- worktree-cli clean --merged-only --force

Create worktrees from SPEC list:
- Read SPEC IDs from file
- Run new command for each

### Shell Aliases

Recommended aliases for .bashrc or .zshrc:
- mw: Short for worktree-cli
- mwl: List worktrees
- mws: Switch to worktree
- mwg: Navigate with eval pattern
- mwsync: Sync current worktree
- mwclean: Clean merged worktrees

### Git Hooks Integration

Post-checkout hook actions:
- Detect worktree environment
- Update last access time in registry
- Check if sync needed with base branch
- Load worktree-specific environment

Pre-push hook actions:
- Detect if pushing from worktree
- Check for uncommitted changes
- Verify sync status with base
- Update registry with push timestamp

---

Version: 2.0.0
Last Updated: 2026-01-06
Module: Complete CLI command reference with usage examples
