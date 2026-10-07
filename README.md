# NemoFleet

System 1 / System 2 cognition for robot fleets, built for the Nebius x NVIDIA Global AI Hackathon (Physical AI track).

- **Reflex (System 1):** Nemotron Nano makes fast per-robot decisions and reports confidence.
- **Motion:** deterministic A* / CBS multi-agent pathfinding handles the geometry.
- **Deliberation (System 2):** Nemotron Ultra on Nebius Token Factory handles escalated, novel anomalies.
- **Perception:** Cosmos Reason interprets camera frames.
- **Red-team at scale:** Nebius Serverless Jobs run thousands of adversarial scenarios to map the cost / latency / success frontier of escalation thresholds.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system map, escalation sequence, and module layout, or the print-ready [PDF](docs/NemoFleet-Architecture.pdf).

Fleet-learning design options inspired by countercurrent heat exchange and ant trails: [docs/NemoFleet-Countercurrent-Options.pdf](docs/NemoFleet-Countercurrent-Options.pdf).

🎬 Explainer video (2.5 min): [docs/NemoFleet-Peer-Learning-Explainer.mp4](docs/NemoFleet-Peer-Learning-Explainer.mp4). Regenerate with `cd docs/video && npm install && npm run build` (macOS, Chrome, ffmpeg).

## Setup

```bash
cp .env.example .env   # add your NEBIUS_API_KEY
```

## License

Apache 2.0
