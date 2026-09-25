# Sarab

Explainable multi-agent AI for building energy management. Intel AI Global
Impact Festival 2026 submission.

## Repo structure

```
sarabintel/
├── agents.py              # the four agents (AC, Lighting, Cost, Comfort)
├── coordinator.py         # negotiation engine
├── simulation.py          # digital-twin simulation, baseline vs. Sarab
├── ml/
│   ├── build_training_data.py   # Phase 1: simulation log -> training table
│   ├── train_model.py           # Phase 2: train, export ONNX, convert to OpenVINO IR
│   └── predictor.py             # loads the OpenVINO model, runs inference
├── models/                # trained model artifacts (committed - small, and
│   ├── occupancy_model.onnx     # regenerating them means re-running training)
│   ├── occupancy_model.xml
│   └── occupancy_model.bin
├── data/                  # generated data (committed as evidence of what
│   ├── simulation_log.csv       # the system actually produces - regenerate
│   └── occupancy_training_data.csv  # anytime by re-running the scripts below)
├── tests/
│   └── test_pipeline.py   # run this before every push
├── requirements.txt
└── .gitignore
```


## Setup

```bash
python3 -m venv sarab_env
source sarab_env/bin/activate        # Windows: sarab_env\Scripts\activate
pip install -r requirements.txt
```

## Running everything, in order, from the repo root

```bash
python3 simulation.py              # -> data/simulation_log.csv (9.4% savings, 0 violations)
python3 ml/build_training_data.py  # -> data/occupancy_training_data.csv (835 rows)
python3 ml/train_model.py          # -> models/occupancy_model.{onnx,xml,bin}
python3 tests/test_pipeline.py     # must print "ALL CHECKS PASSED"
```

Current honest model quality (held-out test data): accuracy 0.885, precision
0.812, recall 0.591, F1 0.684. Recall is the weakest.

## Not done yet

- NNCF quantization + measured before/after inference latency
- Wiring `predictor.py` into `simulation.py`'s negotiation loop so the system
  actually pre-cools ahead of predicted occupancy, instead of the model
  existing as a standalone, unused artifact
