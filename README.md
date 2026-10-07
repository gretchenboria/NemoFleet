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

**Implementation plan:** [docs/NEBIUS_PLAN.md](docs/NEBIUS_PLAN.md), agreed by three review agents. Platform feedback is tracked in [docs/FEEDBACK.md](docs/FEEDBACK.md).

## Site and QA

- `site/` holds the public site (overview, demo, console, video, docs). Build with `node site/build.cjs` (output in `site/dist/`, not committed).
- `tests/qa.cjs` is the QA suite: secret scan, syntax checks, build, link check, and browser checks of every page at three widths in light and dark. Deploy only when it exits 0:

```bash
cd docs/video && npm install && cd ../..
node tests/qa.cjs && npx wrangler pages deploy site/dist --project-name nemofleet
```

## Setup

```bash
cp .env.example .env   # add your NEBIUS_API_KEY
```

## License

Apache 2.0
