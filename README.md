# NemoFleet

System 1 / System 2 cognition for robot fleets, built for the Nebius x NVIDIA Global AI Hackathon (Physical AI track).

- **Reflex (System 1):** Nemotron Nano makes fast per-robot decisions and reports confidence.
- **Motion:** deterministic A* / CBS multi-agent pathfinding handles the geometry.
- **Deliberation (System 2):** Nemotron Ultra on Nebius Token Factory handles escalated, novel anomalies.
- **Perception:** Cosmos Reason interprets camera frames.
- **Red-team at scale:** Nebius Serverless Jobs run thousands of adversarial scenarios to map the cost / latency / success frontier of escalation thresholds.

## Setup

```bash
cp .env.example .env   # add your NEBIUS_API_KEY
```

## License

Apache 2.0
