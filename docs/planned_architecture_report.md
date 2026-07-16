# Planned Architecture – Multi-Agent Coding System

## 1. Goal

Refactor the current agent system from a generic multi-purpose coding loop into a **stateful app-building harness** with:

- a **strict state-machine supervisor**
- a **shared base coding runtime**
- specialized **frontend** and **backend** workers
- a **domain-aware critic / reviewer**
- persistent **project context, task history, and critic feedback**

The system should be able to build **good frontend + suitable backend** without falling into:
- repeated routing loops
- stale plan re-execution
- generic template-heavy frontend output
- weak verification where “code runs” is mistaken for “task is actually done”

---

# 2. Core Architectural Principle

Separate the system into **five layers**:

1. **Reasoning Layer**  
   Understand the user request, break work into manageable tasks, and decide execution order.

2. **Planning Layer**  
   Define product context, architecture, UI direction, and implementation roadmap.

3. **Execution Layer**  
   Perform frontend and backend implementation through specialized workers built on top of one shared coding runtime.

4. **Verification Layer**  
   Critique the implementation for both technical correctness and design / UX quality, then produce structured feedback.

5. **Memory Layer**  
   Persist project context, task history, findings, and infrastructure state so the system does not depend on fragile conversation memory.

---

# 3. High-Level Flow

```text
User Request
    ↓
Architect / Project Context Creation
    ↓
Supervisor (strict state machine)
    ↓
Frontend Worker / Backend Worker / Future Specialists
    ↓
Code Critic & Reviewer
    ↓
Supervisor
    ↓
Done / Next Task / Retry / Replan
```

The **Supervisor** owns workflow truth.  
The **Workers** own implementation.  
The **Critic** owns validation signals.  
The **Memory layer** preserves state across the whole run.

---

# 4. Main Components

## 4.1 Supervisor (State Machine)

### Responsibility
The Supervisor is **not** a creative planner. It is the **deterministic workflow controller**.

### It should own:
- task queue / task plan
- task IDs and task fingerprints
- task status transitions
- routing to the correct worker
- retry / validation handling
- stopping conditions
- optional safe parallel task handling

### Task lifecycle
Each task should move through a deterministic state machine:

```text
PENDING → IN_PROGRESS → DONE
                 ↓
             BLOCKED / FAILED
```

### Suggested task fields
```python
{
  "id": "task_001",
  "title": "Build portfolio homepage",
  "description": "Create hero, projects section, and responsive layout",
  "status": "pending",
  "assigned_agent": None,
  "attempt_count": 0,
  "fingerprint": "...",
  "last_result_summary": ""
}
```

### Key rules
- never reopen a task already marked `done`
- critic output drives state transition
- routing should use **task identity**, not string equality
- plan state must survive message truncation

---

## 4.2 Architect (Planning Layer)

### Responsibility
The Architect is a **blueprint generator**, not a coder.

It should run near the beginning of a project and produce the durable **project context**.

### It should decide:
- product goal
- feature scope
- tech stack
- frontend design direction
- backend boundaries
- API contracts / data flow
- implementation roadmap

### Output
The Architect should populate `project_context`.

---

## 4.3 Project Context (Memory Layer)

### Responsibility
Project Context stores the durable understanding of **what we are building**.

This is critical because otherwise the system remembers files and tasks, but not the actual product.

### Suggested structure
```python
project_context = {
  "name": "...",
  "goal": "...",
  "target_users": "...",
  "tech_stack": "...",
  "design_language": "...",
  "architecture": "...",
  "coding_standards": [...],
  "decisions": [...]
}
```

### It should contain
- project goal / product description
- tech stack
- UI / design direction
- architecture decisions
- coding standards
- important past decisions and patterns

---

# 5. Worker Stack (Execution Layer)

The execution layer should be built around **one shared coding runtime** plus specialized wrappers.

---

## 5.1 Base Coding Worker / Harness

### Responsibility
This is the **shared implementation engine** used by all specialized workers.

### It should own:
- file reading / writing
- precise code modifications
- code retrieval and repository analysis
- shell / safe command execution
- retry loops
- test / lint / validation hooks
- context compaction / summarization
- shared tool calling logic

### Important design rule
Do **not** duplicate this loop across multiple workers.

Instead, expose a builder like:

```python
build_coding_worker_node(
    worker_name="frontend_worker",
    system_prompt=FRONTEND_SYSTEM_PROMPT,
    domain="frontend"
)
```

---

## 5.2 Frontend Worker

### Responsibility
The Frontend Worker is specialized in:
- React / frontend implementation
- component structure
- responsive layout
- UI hierarchy
- styling / Tailwind
- interactions / animation restraint
- frontend polish

### It should not just “write React”.
It should also:
- preserve or infer design language
- avoid generic template layouts
- keep visual consistency across the app
- think in terms of user experience, not just code files

### Frontend output quality bar
- premium but appropriate UI
- good spacing / hierarchy
- reusable components
- strong mobile responsiveness
- consistent design system

---

## 5.3 Backend Worker

### Responsibility
The Backend Worker is specialized in:
- Python / FastAPI / backend implementation
- API routes
- schemas / models
- services / business logic
- auth / validation
- async correctness
- backend architecture

### Backend quality bar
- clean separation between routes, services, and data access
- clear request / response contracts
- explicit validation and error handling
- maintainable structure
- suitable scalability without overengineering tiny features

---

## 5.4 Future Specialist Workers (Optional)

These are **not required now**, but the architecture should leave room for them.

Possible future specialists:
- DevOps / deployment worker
- Database specialist
- Documentation writer
- Test engineer
- Browser / UI validation worker

The key point: **add specialists only when a real bottleneck appears**, not because multi-agent systems are fashionable.

---

# 6. Critic & Reviewer (Verification Layer)

## Responsibility
The critic should be more than a syntax checker.  
It should validate:

1. **technical quality**
2. **design / UX quality**
3. **consistency with project context and user goal**

### Suggested structured output
```python
{
  "status": "VALIDATED" | "NEEDS_CHANGES" | "FAILED_REPEATEDLY",
  "target_worker": "frontend_worker" | "backend_worker",
  "technical_feedback": [...],
  "design_feedback": [...],
  "summary": "..."
}
```

---

## Critic duties by domain

### For frontend tasks
Check:
- visual hierarchy
- responsiveness
- component consistency
- generic / template-heavy sections
- accessibility basics
- alignment with design direction

### For backend tasks
Check:
- route and service structure
- validation and schema correctness
- auth / security issues
- async / DB handling
- integration correctness
- maintainability

### For full-stack tasks
Check both, but keep feedback separated.

---

## Critic as a control signal
The critic must drive state transitions.

### If status is `VALIDATED`
- mark current task `done`

### If status is `NEEDS_CHANGES`
- keep task `in_progress`
- store feedback
- reroute to the correct worker

### If status is `FAILED_REPEATEDLY`
- mark task `blocked` or escalate to replanning

---

# 7. Memory & Infrastructure Layer

This is where the system stops being “just a chat loop” and starts behaving like an actual harness.

## 7.1 Blackboard / Scratchpad
Used for:
- findings
- intermediate notes
- decisions
- artifacts
- task summaries

## 7.2 Task History
Compact summaries of what happened:

```python
task_history = [
  {
    "task_id": "task_12",
    "worker": "frontend_worker",
    "status": "done",
    "summary": "Implemented landing page hero and project cards"
  }
]
```

## 7.3 Critic Feedback Store
Structured review output that the Supervisor can reuse.

```python
critic_feedback = {
  "status": "NEEDS_CHANGES",
  "target_worker": "frontend_worker",
  "technical_feedback": [...],
  "design_feedback": [...]
}
```

## 7.4 Infrastructure / Persistence
Suggested infrastructure pieces:
- vector DB / code index / RAG store
- repo filesystem
- task state store
- logs / observability

---

# 8. Tools & Capabilities Layer

The workers should sit on top of a broad tool layer.

## Suggested shared capabilities
- file IO
- safe terminal commands
- code search / retrieval
- AST / symbol analysis
- dependency analysis
- scaffolding helpers
- security audit tools
- test / validation commands
- optional web search / scraping when relevant

### Important note
Frontend and backend workers should **share the same tool layer**.  
The specialization should come from:
- worker prompts / profiles
- routing
- critic feedback
- domain-aware retrieval

Not from artificially crippling one worker’s tool access.

---

# 9. Domain-Aware Retrieval

This is one of the biggest practical improvements to make.

The base worker should not retrieve context the same way for every task.

## Frontend task retrieval should prioritize
- React components
- Tailwind / CSS
- layout files
- hooks
- assets
- design-related code

## Backend task retrieval should prioritize
- API routes
- services
- models / schemas
- config
- DB access
- auth logic

## Documentation / architecture tasks should prioritize
- README / docs
- config docs
- architectural notes

This is how the same harness becomes smarter without adding ten new agents.

---

# 10. Safe Parallelism

Parallelism is useful, but only when tasks are truly independent.

## Good candidates
- separate frontend sections that do not touch the same components
- independent backend endpoints
- docs or tests alongside implementation

## Bad candidates
- multiple workers editing the same layout / config / shared contract
- frontend and backend changing the same shared types simultaneously

## Recommendation
Parallel execution should be allowed only for tasks explicitly marked:

```python
parallel_safe = True
```

Optional later:
```python
owned_paths = [...]
```

to reduce file collisions.

---

# 11. Recommended State Schema

At minimum, the workflow state should contain:

```python
state = {
  "plan": [...],
  "current_task": "...",
  "current_task_id": "...",
  "last_validated_task_id": "...",
  "next_agent": "...",
  "project_context": {...},
  "critic_feedback": {...},
  "task_history": [...],
  "scratchpad": "...",
}
```

## Additional recommended field
```python
current_task_domain = "frontend" | "backend" | "fullstack" | "unknown"
```

This makes critic behavior and routing much cleaner.

---

# 12. Recommended Execution Flow

## 12.1 Initial project request
1. User provides app / feature request
2. Architect creates project context and roadmap
3. Supervisor creates initial structured task plan

## 12.2 Frontend task flow
```text
Supervisor
  → Frontend Worker
  → Critic
  → Supervisor
```

## 12.3 Backend task flow
```text
Supervisor
  → Backend Worker
  → Critic
  → Supervisor
```

## 12.4 Full-stack project flow
Supervisor decomposes work into:
- frontend tasks
- backend tasks
- integration tasks
- optional polish / validation tasks

Then routes each to the correct worker.

---

# 13. What to Keep, What to Change

## Keep
- strict state-machine supervisor
- shared base coding runtime
- frontend / backend worker split
- one domain-aware critic
- task IDs, fingerprints, and deterministic status transitions

## Change / Improve
- add Architect / Project Context layer
- store critic feedback in structured state
- add task history
- make retrieval domain-aware
- stop relying on prompts alone for specialization
- move toward worker profiles / operating modes instead of just prompt injection
- let critic evaluate implementation **against product intent**, not just against syntax

---

# 14. Implementation Phases

## Phase 1 — Stabilize workflow
- replace old supervisor with strict supervisor
- extract `base_coding_worker`
- add `frontend_worker` and `backend_worker`
- upgrade critic to structured domain-aware output
- update workflow routing
- add `current_task_domain`, `critic_feedback`, `task_history`

## Phase 2 — Improve output quality
- add `project_context`
- add Architect planning step
- add domain-aware retrieval
- add frontend / backend self-review checklists
- improve critic review quality

## Phase 3 — Add safe speedups
- support safe parallel tasks
- track owned paths
- add more specialist workers only if necessary

---

# 15. Final Recommendation

The project should evolve into a **stateful coding harness with specialized implementation modes**, not a multi-agent chat loop.

## The final target architecture is:

- **Supervisor** → strict state machine and workflow truth
- **Architect** → project blueprint and durable project context
- **Base Coding Harness** → shared implementation engine
- **Frontend Worker** → opinionated UI / UX implementation specialist
- **Backend Worker** → opinionated API / architecture implementation specialist
- **Critic** → technical + design + goal-alignment validation
- **Memory / Infrastructure** → persistent task history, project context, blackboard, and code retrieval

That is the version that gives you:
- reliable task routing
- fewer infinite loops
- better frontend quality
- better backend structure
- more consistent full-stack project execution
