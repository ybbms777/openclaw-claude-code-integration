# OpenClaw × Claude Code — Elite Integration

> Bringing the most valuable engineering practices from Claude Code's leaked source code into OpenClaw, your personal AI assistant.
>
> self-eval · evolve · memory compaction · permission classification · Bash security layer · session hooks

---

## The Story: From a Source Leak to an Engineering Integration

**March 31, 2026** — The complete TypeScript source code of Claude Code was accidentally leaked via an npm sourcemap. The code revealed a production-grade AI Agent engineering system that had never appeared in any official documentation:

| System | Purpose |
|--------|---------|
| **autoDream** | Auto-consolidate memories after 24h + 5 sessions |
| **KAIROS** | Always-on proactive awareness loop |
| **YOLO Classifier** | 4-level Bash command risk assessment, fail-closed |
| **Compression Circuit Breaker** | Prevents auto-compact infinite loops |
| **4-Layer Bash Security** | AST parsing → Regex → Permission rules → OS sandbox |

This system was hardened by a **$2.5B ARR commercial product** running in real production environments.

**This repository** extracts the parts that are genuinely useful for OpenClaw users and packages them as installable skills and configurations — no need to understand the source code, just install and use.

---

## What You Get

### 🔧 8 Installable Skills

| Skill | Function | Trigger |
|-------|----------|---------|
| **self-eval** | Detects anomalies on session end, writes reflection memories | `command:stop` hook |
| **evolve** | Extracts NEVER/MUST rules from reflection memories | Manual or `gateway:startup` |
| **memory-compaction** | Weekly LanceDB cleanup — delete low-value memories, merge similar fragments | cron (Sun 3 AM) |
| **compact-guardian** | Circuit breaker: 3 consecutive compression failures → disable auto-compact + Telegram alert | Auto-monitoring |
| **cache-monitor** | Detects prompt cache invalidation on agent bootstrap | `agent:bootstrap` hook |
| **smart-compact** | LLM-powered session file compression | Manual |
| **yolo-permissions** | 3-tier permission classification (LOW/MEDIUM/HIGH), fail-closed | Auto-integrated into exec |
| **safe-command-execution** | Bash AST parsing + regex validation, detects dangerous commands | Auto-integrated into exec |

### 📜 Configuration Examples

- `SOUL.md` — Persona and expression guidelines (Akino rules)
- `AGENTS.md` — Complete behavior protocol (11 user correction detection rules included)
- `docs/` — 4 design documents explaining the engineering rationale

### 🧪 Test Suite

94 pytest tests covering bash_guard / self_eval / evolve / yolo_classifier

---

## Comparison with Claude Code Original

| Dimension | Claude Code Source | This Integration | Status |
|-----------|-------------------|-----------------|--------|
| autoDream | ✅ 24h+5sessions auto-consolidation | ❌ Requires OpenClaw `session:end` hook | [Issue filed](https://github.com/openclaw/openclaw/issues/60514) |
| YOLO Bash Classification | ✅ 4-level risk, fail-closed | ✅ Implemented | ✅ Available |
| 4-Layer Bash Security | ✅ AST+Regex+Permissions+Sandbox | ✅ AST+Regex implemented, bwrap needs OS-level support | ⚠️ Partial |
| Tool Failure Protocol | ✅ Explicit handling paths | ✅ Written into AGENTS.md | ✅ Available |
| Compression Circuit Breaker | ✅ auto-compact infinite loop protection | ✅ Implemented | ✅ Available |
| 3-Tier Memory Architecture | ✅ LanceDB auto-consolidation | ✅ Scripts in place | ✅ Available |
| evolve Rule Extraction | ❌ None | ✅ Manual trigger | ✅ Available |
| Fork Cache Reuse | ✅ Sub-agents reuse parent prompt cache | ❌ Not supported by MiniMax | ❌ Not feasible |

---

## System Architecture

```
User Conversation
    │
    ├── command:stop ──→ self_eval.py ──→ LanceDB (reflection)
    │
    ├── agent:bootstrap ──→ cache_monitor.py ──→ Static layer change detection
    │
    └── gateway:startup ──→ evolve reminder ──→ Manual rule extraction

─────────────────────────────────────────────────

LanceDB memories table
    │
    ├── Real-time: autoCapture (memory-lancedb-pro plugin)
    │
    ├── Weekly cron ──→ memory_compaction.py ──→ Backup + Delete + Merge
    │
    └── Manual evolve ──→ Rules written to AGENTS.md
```

---

## Quick Install

### Step 1: Install Skills

```bash
# Clone the repo
git clone https://github.com/YOUR_GITHUB_USERNAME/openclaw-claude-code-integration.git
cd openclaw-claude-code-integration

# Install all skills
cp -r skills/* ~/.openclaw/workspace/skills/

# Register hooks
openclaw hooks enable self-eval-hook
openclaw hooks enable cache-monitor-hook
openclaw hooks enable evolve-hook

# Restart Gateway
openclaw gateway restart
```

### Step 2: Copy Configuration Files

```bash
cp SOUL.md ~/.openclaw/workspace/SOUL.md
cp AGENTS.md ~/.openclaw/workspace/AGENTS.md
```

Edit `SOUL.md` Chapter 2 (Chinese expression guidelines) and `AGENTS.md` (personal rules) to match your setup.

### Step 3: Verify

```bash
openclaw skills list | grep -E "self-eval|evolve|compact|cache|yolo|safe"
```

All 8 skills should appear in the list.

---

## Core Design Principles

### Prompt-as-Protocol

The most important engineering philosophy from Claude Code: **never write vague instructions, only write explicit protocols.**

```markdown
# ❌ Vague instruction (ineffective)
Try to be careful with actions involving funds or external sending

# ✅ Explicit protocol (actionable)
NEVER directly modify actions involving funds/positions/external sending. Always generate a change plan first and wait for user confirmation.
```

Rule classification:
- `NEVER` — Prohibited behavior (cannot be bypassed)
- `MUST` — Required behavior
- `ALWAYS` — Must be done every time

### Static/Dynamic Layer Separation (Prompt Cache Optimization)

```
┌─────────────────────────────────────────┐
│  Static Layer (unchanging, hits cache)  │
│  SOUL.md / AGENTS.md / TOOLS.md         │
│  USER.md / IDENTITY.md                  │
│  HEARTBEAT.md                           │
├────────── <!-- DYNAMIC_BOUNDARY --> ─────┤
│  Dynamic Layer (refreshed per turn)     │
│  MEMORY.md                              │
│  LanceDB retrieval results              │
│  Current conversation context           │
└─────────────────────────────────────────┘
```

Insert `<!-- DYNAMIC_BOUNDARY -->` between HEARTBEAT.md and MEMORY.md. Content before the boundary stably hits prompt cache, saving ~6,000-8,000 tokens per conversation turn.

### Prompt Cache Supporting Models

| Model | Cache Mechanism | Setup | Notes |
|-------|----------------|-------|-------|
| **Claude** (Anthropic API) | Native auto-cache | No config needed | Best-in-class, Claude Code exclusive |
| **GPT-4o** (OpenAI API) | Auto-cache | No config needed | Auto-activates > 1024 tokens |
| **Gemini 1.5 Pro** (Google API) | Explicit Context Caching | Manual cache object required | Must pre-create cache |
| **DeepSeek V3/R1** (SiliconFlow) | Supported | Configured on SiliconFlow | MiniMax not yet supported |

> **Current OpenClaw (MiniMax)**: Does not support prompt cache token reuse — MiniMax API does not expose cache token mechanics. The static/dynamic layer architecture is ready; it will activate automatically once the model supports it.

### Tool Failure Protocol

```markdown
On any tool failure:
1. First use memory_recall to search relevant keywords
2. Retry at most 2 times, changing strategy each time
3. If still failing after 2 retries: stop, report the reason, wait for instructions
4. NEVER automatically switch to another tool to bypass the problem
5. High-risk tool failure: stop immediately, send Telegram alert, do not retry
```

Without this protocol, the agent retries indefinitely until tokens are exhausted.

### 3-Tier Memory Architecture

```
Conversation records
    ↓ autoCapture (max 3 entries per turn)
LanceDB atomic memories (real-time write)
    ↓ memory_compaction (weekly)
High-quality memory entries (delete + merge)
    ↓ /evolve (manual trigger)
AGENTS.md permanent rules (behavior change)
```

Three tiers, three time scales: real-time, weekly, monthly. Missing any tier causes the memory system to degrade.

---

## Repository Structure

```
openclaw-claude-code-integration/
├── README.md                          # This file (Chinese)
├── README_EN.md                       # English version
├── SOUL.md                            # Persona & expression guidelines
├── AGENTS.md                          # Complete behavior protocol (11 rules)
├── MANUAL.md                          # User manual
├── SKILL.md                           # Skill development standard
├── skills/
│   ├── self-eval/                    # Self-evaluation script
│   │   └── scripts/self_eval.py
│   ├── evolve/                        # Rule extraction
│   │   └── scripts/evolve.py
│   ├── memory-compaction/             # LanceDB periodic cleanup
│   │   └── scripts/memory_compaction.py
│   ├── compact-guardian/              # Compression circuit breaker
│   │   └── scripts/compact_guardian.py
│   ├── cache-monitor/                # Prompt cache monitoring
│   │   └── scripts/cache_monitor.py
│   ├── smart-compact/                 # LLM-powered compression
│   │   └── scripts/smart_compact.py
│   ├── yolo-permissions/              # 3-tier permission classification
│   │   └── scripts/yolo_classifier.py
│   │   └── scripts/bash_guard.py
│   └── safe-command-execution/        # Bash AST security layer
│       └── scripts/safe_ast_check.py
│       └── skills/bash_ast/           # AST parsing submodule
├── tests/                             # pytest test suite (94 tests)
│   ├── test_bash_guard.py
│   ├── test_self_eval.py
│   ├── test_evolve.py
│   └── test_yolo_classifier.py
└── docs/
    ├── 01-architecture.md             # Design rationale
    ├── 02-prompt-engineering.md       # Prompt engineering comparison
    ├── 03-memory-system.md            # Memory system architecture
    └── 04-session-hooks.md            # Hook registration guide
```

---

## Who Is This For

- **OpenClaw power users**: Copy files directly, adjust personal info per the guide
- **AI Agent developers**: Design patterns and prompt architecture are transferable to other frameworks
- **Anyone interested in AI engineering**: Real production experience extracted from a $2.5B ARR commercial product

---

## Known Limitations

1. **`session:end` hook**: Not supported in current OpenClaw version. [Issue filed](https://github.com/openclaw/openclaw/issues/60514). Currently approximated with `command:stop` — does not fire on timeout/disconnect.
2. **Fork cache reuse**: Claude Code supports sub-agent prompt cache reuse. Not feasible with MiniMax.
3. **OS sandbox layer**: Bash AST security only implements AST parsing + regex validation. Linux namespace/bwrap sandbox requires OS-level support.

---

## ⚠️ Disclaimer

This repository contains **no Claude Code source code**. Only engineering concepts and design patterns are extracted. Claude Code source code copyright belongs to Anthropic PBC.

---

## Acknowledgements

- Claude Code source leak discovery: Chaofan Shou ([@Fried_rice](https://twitter.com/Fried_rice))
- OpenClaw project: Peter Steinberger ([@steipete](https://twitter.com/steipete))
- Compound Engineering plugin: EveryInc ([@EveryInc](https://github.com/EveryInc))

---

## License

MIT — Configuration files and skill templates are free to use and modify.
