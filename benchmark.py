#!/usr/bin/env python3
"""
Benchmarking script for local LLMs using Ollama on international food recall data.

Tests a 3-agent sequential pipeline per model:
  Agent 1: JSON Translator  - normalises all string values to professional English
  Agent 2: Summarizer       - produces a strict 3-sentence crisis summary
  Agent 3: Structuring      - combines summary + source JSON into a canonical schema

Results are written to benchmark_results/<model_slug>/ with per-case files for
each agent step, plus timing_summary.json per model and final_summary.json overall.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import ollama

# ── Configuration ──────────────────────────────────────────────────────────────

MODELS = ["qwen2.5:7b", "llama3:8b", "gemma2:9b"]
TEMPERATURE = 0.1
RESULTS_DIR = Path("benchmark_results")

DATA_FILES = {
    "us": "us_recall.json",
    "france": "france_recall.json",
    "uk": "uk_recall.json",
}

# ── System Prompts ─────────────────────────────────────────────────────────────

AGENT1_SYSTEM = (
    "You are a strict data translation API. You will receive a JSON object containing "
    "international food recall data. Your task is to translate all string values into "
    "professional English. You must preserve the exact JSON structure, nested objects, "
    "and arrays. If the string is already in English, simply output the original string. "
    "Do NOT translate URLs, dates, or boolean values. Return ONLY valid JSON. "
    "Do not include markdown backticks or introductory text."
)

AGENT2_SYSTEM = (
    "You are a crisis communications specialist. Review the provided JSON containing "
    "translated food recall data. Write a highly concise, strict 3-sentence summary. "
    "Sentence 1: State what the product is and where it is from. "
    "Sentence 2: State why it is being recalled and the health risk. "
    "Sentence 3: State the required action for the consumer. "
    "Output ONLY these 3 sentences as plain text."
)

AGENT3_SYSTEM = (
    "You are a data structuring API. You will be provided with a 'Text Summary' and a "
    "'Source JSON' object. Your task is to generate a new JSON object combining this data. "
    "Extract the original URL from the Source JSON. Return ONLY valid JSON matching this "
    "exact schema, with no markdown formatting or extra text: "
    '{"product_name": "string", "summary": "[Insert the exact Text Summary provided]", '
    '"hazard_type": "string", "consumer_action": "string", "country_of_origin": "string", '
    '"original_link": "string"}'
)

# ── Logging Setup ──────────────────────────────────────────────────────────────

def setup_logging(results_dir: Path) -> logging.Logger:
    results_dir.mkdir(exist_ok=True)
    log_path = results_dir / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(__name__)

# ── Data Loading ───────────────────────────────────────────────────────────────

def load_test_cases() -> list[dict]:
    """Load and flatten test cases from all three source files."""
    test_cases = []

    with open(DATA_FILES["us"], encoding="utf-8") as f:
        for i, entry in enumerate(json.load(f)):
            test_cases.append({"source": "us", "index": i, "data": entry})

    with open(DATA_FILES["france"], encoding="utf-8") as f:
        for i, entry in enumerate(json.load(f)["results"]):
            test_cases.append({"source": "france", "index": i, "data": entry})

    with open(DATA_FILES["uk"], encoding="utf-8") as f:
        for i, entry in enumerate(json.load(f)["items"]):
            test_cases.append({"source": "uk", "index": i, "data": entry})

    return test_cases

# ── Agent Runners ──────────────────────────────────────────────────────────────

def run_agent1(
    model: str, raw_entry: dict
) -> tuple[dict | None, float, str]:
    """Translate all string values to professional English, return parsed dict."""
    start = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": AGENT1_SYSTEM},
            {"role": "user", "content": json.dumps(raw_entry, ensure_ascii=False)},
        ],
        options={"temperature": TEMPERATURE},
        format="json",
    )
    elapsed = time.perf_counter() - start
    raw_text = response["message"]["content"]

    try:
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")
        return parsed, elapsed, raw_text
    except (json.JSONDecodeError, ValueError):
        return None, elapsed, raw_text


def run_agent2(model: str, agent1_output: dict) -> tuple[str, float]:
    """Produce a 3-sentence crisis communications summary."""
    start = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": AGENT2_SYSTEM},
            {"role": "user", "content": json.dumps(agent1_output, ensure_ascii=False)},
        ],
        options={"temperature": TEMPERATURE},
    )
    elapsed = time.perf_counter() - start
    return response["message"]["content"].strip(), elapsed


def run_agent3(
    model: str, agent1_output: dict, agent2_output: str
) -> tuple[dict | None, float, str]:
    """Combine summary and source JSON into the canonical structured schema."""
    user_content = (
        f"Text Summary: {agent2_output}\n"
        f"Source JSON: {json.dumps(agent1_output, ensure_ascii=False)}"
    )
    start = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": AGENT3_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        options={"temperature": TEMPERATURE},
        format="json",
    )
    elapsed = time.perf_counter() - start
    raw_text = response["message"]["content"]

    try:
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("Response is not a JSON object")
        return parsed, elapsed, raw_text
    except (json.JSONDecodeError, ValueError):
        return None, elapsed, raw_text

# ── Result Persistence ─────────────────────────────────────────────────────────

def save_agent_output(
    model_dir: Path,
    case_id: str,
    agent_num: int,
    content,
    is_failure: bool = False,
    failure_msg: str = "",
) -> None:
    """Write a single agent's output (or failure log) to disk."""
    if is_failure:
        path = model_dir / f"{case_id}_agent{agent_num}_FAILURE.txt"
        path.write_text(
            f"FAILURE: {failure_msg}\n\nRaw LLM response:\n{content}",
            encoding="utf-8",
        )
    elif isinstance(content, dict):
        path = model_dir / f"{case_id}_agent{agent_num}.json"
        path.write_text(
            json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        path = model_dir / f"{case_id}_agent{agent_num}.txt"
        path.write_text(content, encoding="utf-8")

# ── Pipeline Runner ────────────────────────────────────────────────────────────

def run_pipeline_for_case(
    model: str,
    model_dir: Path,
    case: dict,
    log: logging.Logger,
) -> dict:
    """
    Execute the full 3-agent pipeline for a single test case.
    Returns a timing/status record for that case.
    """
    source = case["source"]
    idx = case["index"]
    raw_entry = case["data"]
    case_id = f"{source}_{idx:02d}"
    timing: dict = {"case_id": case_id, "source": source}

    log.info(f"  [{case_id}] Agent 1: JSON Translator ...")
    a1_result, a1_time, a1_raw = run_agent1(model, raw_entry)
    timing["agent1_seconds"] = round(a1_time, 3)

    if a1_result is None:
        msg = "JSON Format Failure - Agent 1"
        log.warning(f"  [{case_id}] {msg}")
        save_agent_output(model_dir, case_id, 1, a1_raw, is_failure=True, failure_msg=msg)
        timing.update(
            agent1_status="FAILURE",
            agent2_status="SKIPPED",
            agent3_status="SKIPPED",
        )
        return timing

    save_agent_output(model_dir, case_id, 1, a1_result)
    timing["agent1_status"] = "SUCCESS"
    log.info(f"  [{case_id}] Agent 1 done in {a1_time:.2f}s")

    log.info(f"  [{case_id}] Agent 2: Summarizer ...")
    a2_result, a2_time = run_agent2(model, a1_result)
    timing["agent2_seconds"] = round(a2_time, 3)
    timing["agent2_status"] = "SUCCESS"
    save_agent_output(model_dir, case_id, 2, a2_result)
    log.info(f"  [{case_id}] Agent 2 done in {a2_time:.2f}s")

    log.info(f"  [{case_id}] Agent 3: Structuring Agent ...")
    a3_result, a3_time, a3_raw = run_agent3(model, a1_result, a2_result)
    timing["agent3_seconds"] = round(a3_time, 3)

    if a3_result is None:
        msg = "JSON Format Failure - Agent 3"
        log.warning(f"  [{case_id}] {msg}")
        save_agent_output(model_dir, case_id, 3, a3_raw, is_failure=True, failure_msg=msg)
        timing["agent3_status"] = "FAILURE"
    else:
        save_agent_output(model_dir, case_id, 3, a3_result)
        timing["agent3_status"] = "SUCCESS"
        log.info(f"  [{case_id}] Agent 3 done in {a3_time:.2f}s")

    timing["total_seconds"] = round(a1_time + a2_time + a3_time, 3)
    log.info(f"  [{case_id}] Total pipeline: {timing['total_seconds']:.2f}s")
    return timing

# ── Summary Helpers ────────────────────────────────────────────────────────────

def compute_model_stats(model: str, timings: list[dict]) -> dict:
    total = len(timings)
    a1_ok = [t for t in timings if t.get("agent1_status") == "SUCCESS"]
    a3_ok = [t for t in timings if t.get("agent3_status") == "SUCCESS"]

    def safe_avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    return {
        "model": model,
        "total_cases": total,
        "agent1_success_rate": f"{len(a1_ok)}/{total}",
        "full_pipeline_success_rate": f"{len(a3_ok)}/{total}",
        "avg_agent1_seconds": safe_avg([t["agent1_seconds"] for t in timings if "agent1_seconds" in t]),
        "avg_agent2_seconds": safe_avg([t["agent2_seconds"] for t in a1_ok if "agent2_seconds" in t]),
        "avg_agent3_seconds": safe_avg([t["agent3_seconds"] for t in a3_ok if "agent3_seconds" in t]),
        "avg_total_pipeline_seconds": safe_avg([t["total_seconds"] for t in a3_ok if "total_seconds" in t]),
    }


def print_model_summary(stats: dict, log: logging.Logger) -> None:
    log.info(f"\n  {stats['model']}:")
    log.info(f"    Agent 1 success:         {stats['agent1_success_rate']}")
    log.info(f"    Full pipeline success:   {stats['full_pipeline_success_rate']}")
    log.info(f"    Avg Agent 1 time:        {stats['avg_agent1_seconds']}s")
    log.info(f"    Avg Agent 2 time:        {stats['avg_agent2_seconds']}s")
    log.info(f"    Avg Agent 3 time:        {stats['avg_agent3_seconds']}s")
    log.info(f"    Avg total pipeline:      {stats['avg_total_pipeline_seconds']}s")

# ── Entry Point ────────────────────────────────────────────────────────────────

def run_benchmark() -> None:
    log = setup_logging(RESULTS_DIR)

    test_cases = load_test_cases()
    source_counts = {s: sum(1 for c in test_cases if c["source"] == s) for s in DATA_FILES}
    log.info(
        f"Loaded {len(test_cases)} test cases  "
        f"(US: {source_counts['us']}, France: {source_counts['france']}, UK: {source_counts['uk']})"
    )

    all_stats: list[dict] = []

    for model in MODELS:
        log.info(f"\n{'=' * 60}")
        log.info(f"MODEL: {model}")
        log.info(f"{'=' * 60}")

        model_slug = model.replace(":", "_").replace(".", "_")
        model_dir = RESULTS_DIR / model_slug
        model_dir.mkdir(exist_ok=True)

        timings: list[dict] = []
        for case in test_cases:
            record = run_pipeline_for_case(model, model_dir, case, log)
            timings.append(record)

        (model_dir / "timing_summary.json").write_text(
            json.dumps(timings, indent=2), encoding="utf-8"
        )

        stats = compute_model_stats(model, timings)
        all_stats.append(stats)
        print_model_summary(stats, log)

    log.info(f"\n{'=' * 60}")
    log.info("BENCHMARK COMPLETE - FINAL SUMMARY")
    log.info(f"{'=' * 60}")
    for stats in all_stats:
        print_model_summary(stats, log)

    final_path = RESULTS_DIR / "final_summary.json"
    final_path.write_text(json.dumps(all_stats, indent=2), encoding="utf-8")
    log.info(f"\nFinal summary saved to {final_path}")


if __name__ == "__main__":
    run_benchmark()
