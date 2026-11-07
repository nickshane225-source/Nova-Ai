"""
Plan Mode Coordinator for Nova AI.
Inspired by PocketPaw's autonomous multi-step execution loop.
Zero third-party pip dependencies - Python standard library only.
"""
import re
from typing import Any, Callable, Dict, List, Optional


def parse_plan_tag(raw_arg: str) -> Dict[str, Any]:
    """
    Parses a PLAN tool argument into a title and list of sequential steps.
    Supports pipe-delimited ('Title | Step 1 | Step 2') and newline-delimited formats.
    """
    raw_arg = (raw_arg or "").strip()
    if not raw_arg:
        return {"title": "Execution Plan", "steps": []}

    # If newlines exist, parse line by line
    lines = [line.strip() for line in raw_arg.splitlines() if line.strip()]
    if len(lines) > 1 and ("|" not in lines[0] or "\n" in raw_arg):
        title = lines[0].lstrip("#").strip()
        steps: List[str] = []
        for line in lines[1:]:
            # Clean leading bullet points or numbered lists if needed
            cleaned = line.strip()
            if cleaned:
                steps.append(cleaned)
        return {"title": title or "Execution Plan", "steps": steps}

    # Pipe-delimited parsing
    parts = [p.strip() for p in raw_arg.split("|") if p.strip()]
    if not parts:
        return {"title": "Execution Plan", "steps": []}

    title = parts[0]
    steps = parts[1:]
    return {"title": title, "steps": steps}


def execute_plan_batch(
    plan: Dict[str, Any],
    cfg: Optional[Dict[str, Any]] = None,
    runner: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """
    Sequentially executes each step in the plan.
    Aborts immediately upon first step failure (fail-fast architecture).
    """
    cfg = cfg or {}
    steps = plan.get("steps") or []
    completed: List[str] = []
    step_results: List[Any] = []

    for idx, step in enumerate(steps, 1):
        try:
            if runner is not None:
                res = runner(step)
            else:
                res = f"Step {idx} ({step}): OK"

            # Check if returned result indicates failure
            if isinstance(res, dict) and not res.get("ok", True):
                return {
                    "ok": False,
                    "completed": completed,
                    "failed_step": step,
                    "error": res.get("error", "Step reported failure"),
                    "results": step_results,
                }

            completed.append(step)
            step_results.append(res)
        except Exception as e:
            return {
                "ok": False,
                "completed": completed,
                "failed_step": step,
                "error": str(e),
                "results": step_results,
            }

    return {
        "ok": True,
        "completed": completed,
        "results": step_results,
    }
