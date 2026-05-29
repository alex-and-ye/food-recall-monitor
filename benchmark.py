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
import re
import time
from datetime import datetime
from pathlib import Path

import ollama

# ── Configuration ──────────────────────────────────────────────────────────────

# MODELS = ["qwen2.5:7b", "llama3:8b", "gemma2:9b", "qwen2.5:14b"]
MODELS = ["qwen2.5:7b", "qwen2.5:14b"]
RESULTS_DIR = Path("benchmark_results_3")

OLLAMA_OPTIONS = {
    "temperature": 0.0,
    "num_ctx": 4096,
    "num_gpu": 99,  # force max layers on GPU
}

DATA_FILES = {
    "us": "us_recall.json",
    "france": "france_recall.json",
    "uk": "uk_recall.json",
}

# Deterministic country of origin per source API (S2 repair). The source files report
# distribution/sales geography rather than a true country of origin, so an LLM can only
# guess; we derive it from the known data source instead.
COUNTRY_BY_SOURCE = {
    "us": "United States",
    "france": "France",
    "uk": "United Kingdom",
}

# ── System Prompts ─────────────────────────────────────────────────────────────

AGENT1_SYSTEM = (
    "You are a strict data translation agent. You will receive a JSON object containing "
    "international food recall data. Translate ALL non-English *string values* and strings inside arrays "
    "into professional English. "
    "This applies to string values only. JSON keys must remain EXACTLY as in the input.\n"
    "Follow these rules exactly:\n"
    "1. TRANSLATE only string values and strings inside arrays.\n"
    "2. DO NOT TRANSLATE: JSON keys, URLs, ISO dates, numeric strings, boolean strings, "
    "phone numbers, email addresses, product codes, batch codes, and brand names.\n"
    "3. DO NOT add, remove, reorder, or rename any JSON fields or keys. The output must have "
    "exactly the same keys and structure as the input.\n"
    "4. Return ONLY valid JSON. No markdown, no commentary, no extra text.\n"
    "5. If a string is already in English, copy it unchanged.\n"
    "Example input:\n"
    '{"categorie_produit": "lait et produits laitiers", "motif_rappel": "detection listeria"}\n'
    "Correct output:\n"
    '{"categorie_produit": "milk and dairy products", "motif_rappel": "Listeria detection"}\n\n'
)

AGENT2_SYSTEM = (
    "You are a crisis communications specialist. Review the provided JSON containing "
    "translated food recall data. Write a summary that is EXACTLY three sentences. "
    "Sentence 1: State what the product is and where it is from. "
    "Sentence 2: State why it is being recalled and the health risk. "
    "Sentence 3: State the required action for the consumer.\n"
    "Strict output rules:\n"
    "1. Output ONLY the three sentences as a single plain-text paragraph.\n"
    "2. Do NOT add any preamble, heading, label, or closing remark "
    "(for example, do not write 'Here is the summary:').\n"
    "3. Produce exactly three sentences, each ending with a period. Do not merge two "
    "sentences into one, and do not add a fourth.\n"
    "4. Do NOT include phone numbers, emails, URLs, batch codes, or lot numbers.\n"
    "5. Use the product's commercial name only; do not append the manufacturer or location "
    "to the product name."
)

AGENT3_SYSTEM = (
    "You are a data structuring API. You will be provided with a 'Text Summary' and a "
    "'Source JSON' object. Generate a new JSON object combining this data. "
    "Return ONLY valid JSON matching this exact schema, with no markdown formatting or extra text:\n"
    '{"product_name": "string", "summary": "string", "hazard_type": "string", '
    '"consumer_action": "string", "country_of_origin": "string", "original_link": "string"}\n'
    "Field rules:\n"
    "1. product_name: the commercial product name only. Do NOT include the manufacturer, "
    "location, batch number, or lot number.\n"
    "2. summary: copy the provided Text Summary VERBATIM, character for character. Do not "
    "rewrite, shorten, expand, or regenerate it.\n"
    "3. hazard_type: a short noun phrase naming the hazard (for example 'Listeria "
    "monocytogenes', 'Undeclared milk', 'Glass'). Do not include explanatory parentheticals "
    "or the words 'presence of'. This field must never be empty.\n"
    "4. consumer_action: a single plain-English sentence. If the source uses pipe ('|') "
    "separated values, convert them into one natural sentence. Never output pipe characters.\n"
    "5. country_of_origin: the country the product originates from or was issued by. Use a "
    "single country name (for example 'France', 'United Kingdom', 'United States'). Do NOT "
    "use distribution scope, sales regions, or sub-national areas. If it cannot be determined, "
    "use 'Unknown'.\n"
    "6. original_link: copy the canonical recall-notice URL from the Source JSON exactly as "
    "written. Prefer the main recall/alert page over PDF or image links. Never invent or "
    "translate a URL."
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

# ── Validation Helpers (measurement: S3 / S4 / S5) ─────────────────────────────

_PREAMBLE_PATTERN = re.compile(
    r"^\s*(here\s+(is|are)\b|sure\b|summary\s*:|below\s+is\b).*?(:|\n)",
    re.IGNORECASE | re.DOTALL,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def evaluate_summary(text: str) -> dict:
    """S4: detect a leading preamble and count sentences. Does not modify the text."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    has_preamble = bool(_PREAMBLE_PATTERN.match(first_line)) or (
        ":" in first_line and len(first_line) < 80 and not first_line.endswith(".")
    )

    body = text.strip()
    sentences = [s for s in _SENTENCE_SPLIT.split(body) if s.strip()]
    sentence_count = len(sentences)

    return {
        "has_preamble": has_preamble,
        "sentence_count": sentence_count,
        "three_sentences": sentence_count == 3,
    }


def url_in_source(url, raw_entry: dict) -> bool:
    """S3: check whether a model-returned URL actually exists in the source entry."""
    if not isinstance(url, str) or not url.strip():
        return False
    return url.strip() in json.dumps(raw_entry, ensure_ascii=False)

# ── Agent Runners ──────────────────────────────────────────────────────────────

def run_agent1(
    model: str, raw_entry: dict
) -> tuple[dict | None, float, str]:
    """Translate all keys and string values to professional English, return parsed dict."""
    start = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": AGENT1_SYSTEM},
            {"role": "user", "content": json.dumps(raw_entry, ensure_ascii=False)},
        ],
        options=OLLAMA_OPTIONS,
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
        options=OLLAMA_OPTIONS,
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
        options=OLLAMA_OPTIONS,
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

    # S4 (measure): flag preamble + sentence-count compliance without altering output.
    summary_eval = evaluate_summary(a2_result)
    timing["agent2_has_preamble"] = summary_eval["has_preamble"]
    timing["agent2_sentence_count"] = summary_eval["sentence_count"]
    timing["agent2_three_sentences"] = summary_eval["three_sentences"]
    if summary_eval["has_preamble"]:
        log.warning(f"  [{case_id}] Preamble Warning - Agent 2")
    if not summary_eval["three_sentences"]:
        log.warning(
            f"  [{case_id}] Sentence Count Warning - Agent 2 "
            f"({summary_eval['sentence_count']} sentences)"
        )
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
        # Measurements taken from the model's raw output BEFORE any repair.
        # S3 (measure): did the model return a real URL from the source?
        timing["agent3_link_in_source"] = url_in_source(
            a3_result.get("original_link"), raw_entry
        )
        # S5 (measure): did consumer_action leak pipe-delimited source formatting?
        consumer_action = a3_result.get("consumer_action")
        timing["agent3_consumer_action_has_pipe"] = (
            isinstance(consumer_action, str) and "|" in consumer_action
        )
        # bonus measure: empty hazard_type.
        hazard = a3_result.get("hazard_type")
        timing["agent3_hazard_empty"] = not (isinstance(hazard, str) and hazard.strip())

        if not timing["agent3_link_in_source"]:
            log.warning(f"  [{case_id}] Link Not In Source Warning - Agent 3")
        if timing["agent3_consumer_action_has_pipe"]:
            log.warning(f"  [{case_id}] Pipe Format Warning - Agent 3")
        if timing["agent3_hazard_empty"]:
            log.warning(f"  [{case_id}] Empty hazard_type Warning - Agent 3")

        # S1 (repair): force summary to the verbatim Agent 2 output.
        a3_result["summary"] = a2_result
        # S2 (repair): derive country_of_origin from the known data source.
        a3_result["country_of_origin"] = COUNTRY_BY_SOURCE.get(source, "Unknown")

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

    a2_ok = [t for t in timings if t.get("agent2_status") == "SUCCESS"]

    return {
        "model": model,
        "total_cases": total,
        "agent1_success_rate": f"{len(a1_ok)}/{total}",
        "full_pipeline_success_rate": f"{len(a3_ok)}/{total}",
        "avg_agent1_seconds": safe_avg([t["agent1_seconds"] for t in timings if "agent1_seconds" in t]),
        "avg_agent2_seconds": safe_avg([t["agent2_seconds"] for t in a1_ok if "agent2_seconds" in t]),
        "avg_agent3_seconds": safe_avg([t["agent3_seconds"] for t in a3_ok if "agent3_seconds" in t]),
        "avg_total_pipeline_seconds": safe_avg([t["total_seconds"] for t in a3_ok if "total_seconds" in t]),
        # Quality compliance (measured, not repaired):
        "agent2_clean_summaries": f"{sum(1 for t in a2_ok if t.get('agent2_three_sentences') and not t.get('agent2_has_preamble'))}/{len(a2_ok)}",
        "agent2_preamble_count": sum(1 for t in a2_ok if t.get("agent2_has_preamble")),
        "agent2_wrong_sentence_count": sum(1 for t in a2_ok if not t.get("agent2_three_sentences")),
        "agent3_valid_links": f"{sum(1 for t in a3_ok if t.get('agent3_link_in_source'))}/{len(a3_ok)}",
        "agent3_pipe_leaks": sum(1 for t in a3_ok if t.get("agent3_consumer_action_has_pipe")),
        "agent3_empty_hazard": sum(1 for t in a3_ok if t.get("agent3_hazard_empty")),
    }


def print_model_summary(stats: dict, log: logging.Logger) -> None:
    log.info(f"\n  {stats['model']}:")
    log.info(f"    Agent 1 success:         {stats['agent1_success_rate']}")
    log.info(f"    Full pipeline success:   {stats['full_pipeline_success_rate']}")
    log.info(f"    Avg Agent 1 time:        {stats['avg_agent1_seconds']}s")
    log.info(f"    Avg Agent 2 time:        {stats['avg_agent2_seconds']}s")
    log.info(f"    Avg Agent 3 time:        {stats['avg_agent3_seconds']}s")
    log.info(f"    Avg total pipeline:      {stats['avg_total_pipeline_seconds']}s")
    log.info(f"    Agent 2 clean summaries: {stats['agent2_clean_summaries']} "
             f"(preamble: {stats['agent2_preamble_count']}, "
             f"wrong sentence count: {stats['agent2_wrong_sentence_count']})")
    log.info(f"    Agent 3 valid links:     {stats['agent3_valid_links']} "
             f"(pipe leaks: {stats['agent3_pipe_leaks']}, "
             f"empty hazard: {stats['agent3_empty_hazard']})")

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
