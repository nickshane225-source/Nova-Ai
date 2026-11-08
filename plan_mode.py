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
    runner: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Sequentially executes each step in the plan.
    Caps plan execution at 10 steps.
    Aborts immediately upon first step failure (fail-fast architecture).
    Pauses execution if a step requires user confirmation.
    """
    cfg = cfg or {}
    all_steps = (plan.get("steps") or [])[:10]  # Cap at 10 steps
    completed: List[str] = list(plan.get("completed") or [])
    step_results: List[Any] = list(plan.get("results") or [])

    # If resuming from a paused state, execute remaining_steps, otherwise all_steps
    steps_to_run = plan.get("remaining_steps") if "remaining_steps" in plan else all_steps
    start_offset = len(completed)

    for i, step in enumerate(steps_to_run):
        idx = start_offset + i + 1
        if idx > 10:
            break
        try:
            if runner is not None:
                try:
                    res = runner(step, idx, all_steps, completed, step_results)
                except TypeError:
                    res = runner(step)
            else:
                res = f"Step {idx} ({step}): OK"

            if isinstance(res, dict):
                if res.get("paused"):
                    # Calculate remaining steps strictly after this paused step
                    # If steps_to_run is a sublist, remaining in this batch is steps_to_run[i+1:]
                    rem = steps_to_run[i + 1:]
                    return {
                        "ok": True,
                        "paused": True,
                        "completed": completed,
                        "paused_step": step,
                        "pending_info": res.get("pending_info"),
                        "results": step_results,
                        "remaining_steps": rem,
                    }
                if not res.get("ok", True):
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
