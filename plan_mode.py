"""
Plan Mode Coordinator for Nova AI.
Inspired by PocketPaw's autonomous multi-step execution loop.
Zero third-party pip dependencies - Python standard library only.
"""
import inspect
import re
import time
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
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """
    Sequentially executes each step in the plan.
    Caps plan execution at 10 steps.
    Enforces a 5-minute (300s default) maximum plan runtime.
    Aborts immediately upon first step failure (fail-fast architecture).
    Pauses execution if a step requires user confirmation.
    """
    cfg = cfg or {}
    all_steps = (plan.get("steps") or [])[:10]  # Cap at 10 steps
    completed: List[str] = list(plan.get("completed") or [])
    step_results: List[Any] = list(plan.get("results") or [])

    accumulated_active = float(plan.get("active_seconds", 0.0))
    start_time = plan.get("started_at")
    if start_time is None:
        start_time = time.time()
        plan["started_at"] = start_time

    # If resuming from a paused state, execute remaining_steps, otherwise all_steps
    steps_to_run = plan.get("remaining_steps") if "remaining_steps" in plan else all_steps
    start_offset = len(completed)

    takes_extra_args = False
    if runner is not None:
        try:
            sig = inspect.signature(runner)
            params = list(sig.parameters.values())
            has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
            pos_params = [
                p for p in params
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            takes_extra_args = has_varargs or len(pos_params) >= 5
        except (ValueError, TypeError):
            takes_extra_args = False

    for i, step in enumerate(steps_to_run):
        idx = start_offset + i + 1
        if idx > 10:
            break

        # Check cancel flag between steps
        is_canc = False
        if plan.get("cancelled"):
            is_canc = True
        elif callable(plan.get("is_cancelled")):
            try:
                is_canc = bool(plan["is_cancelled"]())
            except Exception:
                pass
        if is_canc:
            return {
                "ok": False,
                "error": "Plan was cancelled by user.",
                "cancelled": True,
                "failed_step": step,
                "completed": completed,
                "results": step_results,
                "active_seconds": accumulated_active,
            }

        if accumulated_active >= timeout:
            return {
                "ok": False,
                "error": f"Plan execution timed out after {int(accumulated_active)} seconds of active execution (maximum allowed: {int(timeout)}s).",
                "failed_step": step,
                "completed": completed,
                "results": step_results,
                "timed_out": True,
                "active_seconds": accumulated_active,
            }

        # Refuse nested PLAN tags or nested plan steps
        step_str = (step or "").strip().upper()
        if step_str.startswith("PLAN:") or "[[PLAN:" in step_str or "[[PLAN " in step_str:
            return {
                "ok": False,
                "error": "Refused: Nested plans are not allowed. A plan step must never execute another PLAN tag or nested plan.",
                "failed_step": step,
                "completed": completed,
                "results": step_results,
                "active_seconds": accumulated_active,
            }
        try:
            t_step_start = time.time()
            plan["get_active_seconds"] = lambda: accumulated_active + max(0.0, time.time() - t_step_start)
            if runner is not None:
                if takes_extra_args:
                    res = runner(step, idx, all_steps, completed, step_results)
                else:
                    res = runner(step)
            else:
                res = f"Step {idx} ({step}): OK"
            step_duration = max(0.0, time.time() - t_step_start)
            accumulated_active += step_duration
            plan["active_seconds"] = accumulated_active

            step_timeout = float(cfg.get("plan_step_timeout", 60.0))
            if step_duration > step_timeout:
                return {
                    "ok": False,
                    "error": f"Plan step timed out: step '{step}' exceeded per-step timeout of {int(step_timeout)}s (took {step_duration:.1f}s).",
                    "failed_step": step,
                    "completed": completed,
                    "results": step_results,
                    "timed_out": True,
                    "active_seconds": accumulated_active,
                }

            if accumulated_active > timeout:
                return {
                    "ok": False,
                    "error": f"Plan execution timed out after {int(accumulated_active)} seconds of active execution (maximum allowed: {int(timeout)}s).",
                    "failed_step": step,
                    "completed": completed,
                    "results": step_results,
                    "timed_out": True,
                    "active_seconds": accumulated_active,
                }

            if isinstance(res, dict):
                if res.get("paused"):
                    # Calculate remaining steps strictly after this paused step
                    # If steps_to_run is a sublist, remaining in this batch is steps_to_run[i+1:]
                    rem = steps_to_run[i + 1:]
                    p_info = res.get("pending_info") or {}
                    if isinstance(p_info, dict) and "plan_state" in p_info:
                        p_info["plan_state"]["started_at"] = start_time
                        p_info["plan_state"]["active_seconds"] = accumulated_active
                    return {
                        "ok": True,
                        "paused": True,
                        "completed": completed,
                        "paused_step": step,
                        "pending_info": p_info,
                        "results": step_results,
                        "remaining_steps": rem,
                        "started_at": start_time,
                        "active_seconds": accumulated_active,
                    }
                if not res.get("ok", True):
                    return {
                        "ok": False,
                        "completed": completed,
                        "failed_step": step,
                        "error": res.get("error", "Step reported failure"),
                        "results": step_results,
                        "active_seconds": accumulated_active,
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
                "active_seconds": accumulated_active,
            }

    return {
        "ok": True,
        "completed": completed,
        "results": step_results,
        "started_at": start_time,
        "active_seconds": accumulated_active,
    }
