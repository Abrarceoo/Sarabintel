# Sarab (سَرَب)

**Proactive Multi-Agent AI for Greener Buildings** — Intel AI Global Impact Festival 2026, AI Changemakers (18+ category).

Buildings consume ~30% of global energy, and in Saudi Arabia, air conditioning alone drives ~70% of building electricity use and ~70% of national peak demand. Most buildings still cool empty rooms on fixed schedules. Sarab is an explainable multi-agent AI layer that retrofits onto existing building systems — no cloud, no new hardware — and makes real-time, room-by-room energy decisions by negotiating between comfort, lighting, cost, and safety, while predicting occupancy to cool spaces in advance during cheaper, cleaner hours.

## How it works

Four independent agents, each with exactly three methods (`observe`, `propose`, `evaluate`), negotiate every decision through a `Coordinator`:

| Agent | Goal |
|---|---|
| **AC** | Comfortable temperature (~23°C when occupied) |
| **Lighting** | Adequate light — off when empty, dimmed with daylight |
| **Cost** | Lower the bill — pushes toward the warmest still-acceptable setpoint at peak pricing |
| **Comfort** | The guardrail — hard safety limits that are never violated, even in a hospital operating room |

No agent sees another's internal state. The final decision is often one **no single agent proposed** — it's the product of the negotiation itself, and every decision is logged with who proposed what and why it won.

This is classical rule-based negotiation (multi-criteria decision making), **not** an LLM or LangChain-style agent framework. AI enters at exactly one place: predicting occupancy so the system can pre-cool ahead of it.

## Current, honestly-reported results

All numbers are simulation-estimated (one week, 5 zones including an operating room), not measured from a real building:

| Metric | Value |
|---|---|
| Energy savings vs. fixed-schedule baseline | 9.5% |
| Cost savings vs. fixed-schedule baseline | 11.8% |
| Hard-constraint violations | 0 / 1680 decisions |
| Occupancy model (accuracy / precision / recall / F1) | 0.885 / 0.812 / 0.591 / 0.684 |
| OpenVINO (FP32) vs. raw scikit-learn latency | ~1.2x faster |
| NNCF INT8 vs. FP32 latency | ~0.93–0.94x (no benefit at this model size — measured, not assumed) |

Cost savings are reported alongside energy savings deliberately: the system's negotiation and pre-cooling mechanisms shift *when* energy is used toward cheaper hours, which shows up more clearly in cost than in raw kWh.

## Repo structure

```
agents.py, coordinator.py, simulation.py   # the negotiation engine + digital-twin simulation
ml/
  build_training_data.py    # simulation log -> labeled training table
  train_model.py            # train, export to ONNX, convert to OpenVINO IR
  predictor.py              # loads the OpenVINO model, runs real inference
  quantize_and_benchmark.py # NNCF INT8 quantization + measured latency/accuracy
models/                     # occupancy_model.{onnx,xml,bin}, occupancy_model_int8.{xml,bin}
data/                       # simulation_log.csv, occupancy_training_data.csv
tests/
  test_pipeline.py          # 17 checks: regression, ML fidelity, pre-cooling behavior, quantization sanity
requirements.txt
```

Every script resolves its own file paths from its own location, not the current working directory — they work correctly regardless of where you run them from.

## Setup and running, in order

```bash
python3 -m venv sarab_env
source sarab_env/bin/activate        # Windows: sarab_env\Scripts\activate
pip install -r requirements.txt

python3 simulation.py               # digital-twin simulation; bootstraps reactive-only if no model exists yet
python3 ml/build_training_data.py   # -> data/occupancy_training_data.csv
python3 ml/train_model.py           # -> models/occupancy_model.{onnx,xml,bin}
python3 ml/quantize_and_benchmark.py # -> models/occupancy_model_int8.{xml,bin} + latency report
python3 simulation.py               # re-run: now fully proactive, using the trained model
python3 tests/test_pipeline.py      # must print "ALL CHECKS PASSED"
```

(`simulation.py` is listed twice deliberately: the first run has no trained model yet, so it runs reactive-only to produce the log the ML pipeline needs; the second run picks up the trained model and produces the real proactive numbers above.)

## Intel technology pipeline

`scikit-learn` (train) → hand-built ONNX graph (`Gemm` + `Sigmoid`, not scikit-learn's default classifier export — see the implementation report for why) → OpenVINO IR conversion → OpenVINO Runtime inference inside the negotiation loop → NNCF post-training INT8 quantization, measured against the FP32 baseline. Runs entirely on local CPU — no cloud service — which is the edge-AI principle this design depends on regardless of device size.

## What's simulation vs. what's measured

- **Simulation-estimated:** all energy/cost/savings figures, the training data itself (one synthetic week + a separate validation pass against the real-world UCI Occupancy Detection dataset).
- **Actually measured:** model accuracy metrics (on held-out data), inference latency (7 repeated trials, CPU), FP32-vs-INT8 numerical fidelity.
- **Design-only, not yet tested:** deployment against a real building's BMS. The architecture is built to separate the data source and command destination from the agent logic specifically so this becomes a substitution, not a rewrite — but that claim is untested until it happens.

## Known limitations (stated plainly, not hidden)

- Model recall (0.591) means roughly 4 in 10 true "occupied next hour" cases are missed.
- Genuine pre-cooling opportunities are structurally rare (73 across a full week, all 5 zones combined), which bounds how much the proactive mechanism can move the headline numbers regardless of model quality.
- INT8 quantization provides no latency benefit at this model's size — kept and reported anyway, as evidence the full Intel pipeline was executed and honestly measured.

Full technical detail, including every bug found and fixed while building this, is in the implementation report shared separately with the team.
