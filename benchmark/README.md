# Benchmarking Local LLMs for Food Recall Data

Python benchmark that evaluates local open-source LLMs (via [Ollama](https://ollama.com)) on a 3-agent pipeline for international food recall JSON from US, France, and UK APIs.

## Pipeline

For each model and test case:

1. **Agent 1 — JSON Translator** — Translates non-English string values to English; preserves keys and structure (`format="json"`).
2. **Agent 2 — Summarizer** — Produces a strict 3-sentence crisis summary.
3. **Agent 3 — Structuring** — Combines summary + source JSON into a canonical schema (`format="json"`).

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- Models pulled locally, e.g.:

```bash
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b
ollama pull llama3:8b
ollama pull gemma2:9b
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Run

```bash
python benchmark.py
```

Edit `MODEL_BASES`, `DEFAULT_QUANTIZATION`, and `RESULTS_DIR` at the top of `benchmark.py` to change which models are tested and where output is saved.

## Test data

Six cases from three JSON files in `recall_data/`:


| File                              | Cases |
| --------------------------------- | ----- |
| `recall_data/us_recall.json`     | 2     |
| `recall_data/france_recall.json` | 2     |
| `recall_data/uk_recall.json`     | 2     |


## Output

Results are written under `benchmark_results/` (or the configured `RESULTS_DIR`):

```
benchmark_results/
├── final_summary.json          # timing + quality metrics per model
├── benchmark_<timestamp>.log
└── <model_slug>/
    ├── us_00_agent1.json
    ├── us_00_agent2.txt
    ├── us_00_agent3.json
    └── timing_summary.json
```

**Quality metrics** (per case): Agent 2 sentence count and preamble detection; Agent 3 link validity, pipe-delimited `consumer_action`, empty `hazard_type`.

**Repairs** (applied before saving Agent 3 output): `summary` is set verbatim from Agent 2; `country_of_origin` is derived from the data source (`us` / `france` / `uk`).

## Configuration

Key settings in `benchmark.py`:


| Setting                 | Default                                         | Purpose                              |
| ----------------------- | ----------------------------------------------- | ------------------------------------ |
| `MODEL_BASES`           | `qwen2.5:7b`, `llama3:8b`, `gemma2:9b`, `qwen2.5:14b` | Base models to benchmark             |
| `DEFAULT_QUANTIZATION`  | `q4_K_M`                                        | Quantization tag applied to all models |
| `DATA_DIR`              | `recall_data/`                                  | Input JSON directory                 |
| `RESULTS_DIR`           | `benchmark_results`                             | Output directory                     |
| `OLLAMA_OPTIONS`        | `temperature=0.0`, `num_ctx=4096`, `num_gpu=99` | Shared Ollama inference options      |


## Notes

- Agent 1 is the slowest step (large HTML fields); expect most pipeline time there.
- Models run with explicit `q4_K_M` tags (e.g. `qwen2.5:7b-instruct-q4_K_M`); pull those tags before running.
- Automated checks catch formatting issues; semantic errors (e.g. wrong allergen in `hazard_type`) require manual review.

