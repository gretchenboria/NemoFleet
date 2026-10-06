# NemoFleet Architecture

📄 **Print-ready version:** [NemoFleet-Architecture.pdf](NemoFleet-Architecture.pdf)

NemoFleet splits robot-fleet cognition into two speeds, the way people do:

- **System 1 (reflex):** a small, fast model on each robot handles routine events in under a second.
- **System 2 (deliberation):** a large reasoning model in the cloud handles novel or high-stakes events, and only those.

Geometry is never delegated to an LLM. A deterministic planner owns every trajectory, so every path is collision-free by construction. The models decide *what* should happen; the planner decides *how* to move.

---

## 1. System map

```mermaid
flowchart TB
    subgraph UI["Operator Console"]
        CMD["Natural-language commands"]
        VIEW["Live fleet view"]
        LOG["Reasoning and API log"]
        FRONT["Frontier dashboard"]
    end

    subgraph CORE["Fleet Runtime - FastAPI"]
        SIM["World Simulator<br/>warehouse grid, robots, humans, hazards"]
        EVT["Event Bus"]
        MOTION["Motion Layer<br/>A* + CBS multi-agent pathfinding"]
        EXEC["Action Executor<br/>schema-validated actions"]
        MEM[("Precedent Memory")]
    end

    subgraph EDGE["System 1 - per robot"]
        NANO["Reflex Agent<br/>Nemotron Nano"]
        GATE{"Escalation Gate<br/>confidence below threshold<br/>or novel event?"}
    end

    subgraph CLOUD["System 2 - Nebius Token Factory"]
        ULTRA["Deliberator<br/>Nemotron Ultra"]
        COSMOS["Perception<br/>Cosmos Reason VLM"]
    end

    subgraph BATCH["Nebius Serverless Jobs"]
        GEN["Adversarial Scenario Generator<br/>Nemotron"]
        RUN["Parallel headless sim runs"]
        AGG["Metrics: success, latency, cost per task"]
    end

    CMD --> ULTRA
    SIM -- sensor events --> EVT
    SIM -- camera frames --> COSMOS
    COSMOS -- scene description --> EVT
    EVT --> NANO
    MEM -- few-shot precedents --> NANO
    NANO --> GATE
    GATE -- confident --> EXEC
    GATE -- escalate --> ULTRA
    ULTRA -- decision --> EXEC
    ULTRA -- new precedent --> MEM
    EXEC -- goals and constraints --> MOTION
    MOTION -- trajectories --> SIM
    SIM --> VIEW
    NANO --> LOG
    ULTRA --> LOG

    GEN --> RUN --> AGG --> FRONT
    RUN -. uses same runtime .-> CORE
```

---

## 2. Escalation sequence: a person enters a robot lane

```mermaid
sequenceDiagram
    autonumber
    participant S as Simulator
    participant C as Cosmos Reason
    participant N as Nano reflex
    participant G as Escalation Gate
    participant U as Ultra deliberator
    participant M as Motion layer
    participant P as Precedent memory

    S->>C: Camera frame from Robot 3
    C-->>S: "Person kneeling beside fallen box, aisle 4"
    S->>N: Event + local state
    P-->>N: Similar past precedents
    N-->>G: Proposed action: detour, confidence 0.41
    G->>U: Escalate - human present, low confidence
    U-->>G: Halt R3, quarantine aisle 4, reroute R1 and R5, alert supervisor
    G->>M: Validated actions + zone constraints
    M-->>S: New collision-free trajectories
    U->>P: Store decision as precedent
    Note over N,P: The next similar event is handled by Nano without escalating
```

---

## 3. Responsibility split

| Layer | Model or algorithm | Decides | Latency target | Never does |
|---|---|---|---|---|
| Perception | Cosmos Reason | What the camera sees | ~1 s | Plan actions |
| Reflex | Nemotron Nano | Routine responses, plus a confidence score | < 1 s | Handle safety-critical novel events alone |
| Escalation gate | Rules + threshold τ | Whether to call System 2 | ~0 | Generate content |
| Deliberation | Nemotron Ultra | Novel and high-stakes decisions, task re-prioritization | 5–30 s | Produce raw coordinates |
| Motion | A* + CBS | Exact collision-free paths | < 10 ms | Interpret semantics |
| Executor | Pydantic schemas | Whether an action is valid | ~0 | Accept malformed LLM output |

---

## 4. Action schema boundary

The LLMs speak in high-level, schema-validated intents. Anything that fails validation is rejected and retried, never executed.

```mermaid
flowchart LR
    LLM["Nano or Ultra output"] --> V{"Pydantic validation"}
    V -- invalid --> R["Retry with error feedback<br/>max 2"]
    R --> LLM
    V -- valid --> A["FleetAction"]
    A --> T1["goto: robot, target"]
    A --> T2["halt: robot"]
    A --> T3["quarantine_zone: cells, ttl"]
    A --> T4["reassign_task: task, robot"]
    A --> T5["alert_human: severity, message"]
    T1 & T2 & T3 & T4 & T5 --> MOT["Motion layer and simulator"]
```

---

## 5. Red-team frontier pipeline

This produces the headline result: success, latency, and cost across escalation thresholds, comparing Nano-only, Ultra-only, and the hybrid.

```mermaid
flowchart LR
    SEED["Scenario seeds"] --> GEN["Nemotron generates adversarial scenarios<br/>blocked exits, humans in lanes,<br/>conflicting orders, sensor dropout"]
    GEN --> SHARD["Shard across Serverless Jobs"]
    SHARD --> J1["Job: τ = 0.3"]
    SHARD --> J2["Job: τ = 0.5"]
    SHARD --> J3["Job: τ = 0.7"]
    SHARD --> JB["Baselines: Nano-only, Ultra-only"]
    J1 & J2 & J3 & JB --> OUT[("Results CSV / Parquet")]
    OUT --> PLOT["Frontier chart<br/>success vs latency vs cost per task"]
```

---

## 6. Planned module layout

```
nemofleet/
├── models.py          # Pydantic: WorldState, Robot, Event, FleetAction, Decision
├── sim/
│   ├── world.py       # Warehouse grid, robots, humans, hazards, tick loop
│   └── scenarios.py   # Scenario loading and procedural generation
├── motion/
│   ├── astar.py       # Single-agent shortest path
│   └── cbs.py         # Conflict-based search for multi-agent paths
├── cognition/
│   ├── client.py      # Token Factory client (OpenAI-compatible)
│   ├── reflex.py      # Nemotron Nano, System 1
│   ├── deliberator.py # Nemotron Ultra, System 2
│   ├── gate.py        # Escalation policy
│   ├── perception.py  # Cosmos Reason wrapper
│   └── memory.py      # Precedent store and retrieval
├── api/
│   └── server.py      # FastAPI: /state, /command, /inject, /tick, /log
├── ui/                # Operator console
└── jobs/
    ├── redteam.py     # Serverless Job entry point
    └── frontier.py    # Aggregation and charts
```

---

## 7. Where NVIDIA and Nebius are used

| Component | NVIDIA model | Nebius service |
|---|---|---|
| Reflex agent | Nemotron Nano | Token Factory |
| Deliberator | Nemotron Ultra | Token Factory |
| Perception | Cosmos Reason | Token Factory or AI Cloud endpoint |
| Scenario generator | Nemotron Super | Token Factory |
| Red-team runs | — | Serverless Jobs |

Confirm the exact model IDs against the Token Factory catalog before wiring up the client.
