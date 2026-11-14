"""
Budget Manager - AI Token and Model Routing
============================================================================
Controls which AI model to use based on token limits, historical success,
and error rates. It persists state in the global `ai_budget.json` file
at the root of the repository.

Responsibilities
----------------
- Read the current budget state from `ai_budget.json`.
- Reset daily limits if the last run was on a different day.
- Decide which model (Groq, Google Gemma, or Meta Muse Spark) to use for
  table summarization.
- Record token usage and update the remaining limits.
- Adjust future limits based on consecutive successes or failures.
- Implement a circuit breaker: if a model fails N times in a row, skip it
  temporarily and go directly to the next model.

Notes
-----
- The file `ai_budget.json` must exist at the root of the repository.
- If the file is missing or corrupted, a safe default state is created.
- The `last_updated` field follows the ISO 8601 format (UTC).
- Muse Spark is a paid fallback (priority 3). It is only used when both
  Groq and Google are exhausted or have failed repeatedly.

Author: Alfonso Droguett
Repository: https://github.com/adroguetth/youtube-music-charts-intelligence
Email: adroguett.consultor@gmail.com
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# CONSTANTS
# ============================================================================
# Navigate up 4 levels: budget_manager.py -> ai -> core -> 4_report_generator -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
BUDGET_FILE = _REPO_ROOT / "ai_budget.json"

# Default limits (tokens)
DEFAULT_GROQ_LIMIT = 200_000
DEFAULT_GOOGLE_LIMIT = 1_500_000
DEFAULT_MUSE_SPARK_LIMIT = 100_000
DEFAULT_DEEPSEEK_LIMIT = 500_000

# Margins
BONUS_MULTIPLIER = 1.05  # +5% tokens per consecutive success
PENALTY_MULTIPLIER = 0.90  # -10% tokens per consecutive failure

# Circuit breaker: if a model fails N times in a row, mark it as "down"
# for the rest of the run and skip it.
CIRCUIT_BREAKER_THRESHOLD = 3


class BudgetManager:
    def __init__(self):
        self._state = self._load_state()
        # In-memory circuit breaker state (not persisted across runs)
        self._model_failures: dict[str, int] = {
            "groq_gpt_oss": 0,
            "google_gemma": 0,
            "muse_spark": 0,
        }

    def _load_state(self) -> dict:
        """Load the budget state from disk, or create a default one."""
        if BUDGET_FILE.exists():
            try:
                with open(BUDGET_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                # Ensure required keys exist
                if "models" not in state or "status" not in state:
                    raise ValueError("Invalid budget file format")
                return state
            except (json.JSONDecodeError, IOError, ValueError) as e:
                print(f"   [Budget] Warning: Failed to load {BUDGET_FILE}: {e}")
                print("   [Budget] Using default budget.")
        
        return self._create_default_state()

    def _create_default_state(self) -> dict:
        """Create a fresh default budget state."""
        return {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "status": {
                "consecutive_successes": 0,
                "consecutive_failures": 0
            },
            "models": {
                "groq_gpt_oss": {
                    "tokens_remaining": DEFAULT_GROQ_LIMIT,
                    "max_daily_limit": DEFAULT_GROQ_LIMIT,
                    "priority": 1
                },
                "google_gemma": {
                    "tokens_remaining": DEFAULT_GOOGLE_LIMIT,
                    "max_daily_limit": DEFAULT_GOOGLE_LIMIT,
                    "priority": 2
                },
                "muse_spark": {
                    "tokens_remaining": DEFAULT_MUSE_SPARK_LIMIT,
                    "max_daily_limit": DEFAULT_MUSE_SPARK_LIMIT,
                    "priority": 3
                },
                "deepseek_writer": {
                    "tokens_remaining": DEFAULT_DEEPSEEK_LIMIT,
                    "max_daily_limit": DEFAULT_DEEPSEEK_LIMIT,
                    "priority": 4
                }
            }
        }

    def _save_state(self):
        """Persist the current state to disk."""
        self._state["last_updated"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(BUDGET_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except IOError as e:
            print(f"   [Budget] Warning: Failed to save {BUDGET_FILE}: {e}")

    def _reset_daily_limits_if_needed(self):
        """Reset daily limits if the last run was on a different day."""
        last_updated_str = self._state.get("last_updated", "")
        if not last_updated_str:
            return
            
        try:
            last_updated = datetime.fromisoformat(last_updated_str)
            now = datetime.now(timezone.utc)
            
            # If the calendar day changed, reset daily limits
            if last_updated.date() < now.date():
                print("   [Budget] New day detected. Resetting daily token limits.")
                for model in self._state["models"].values():
                    model["tokens_remaining"] = model["max_daily_limit"]
                self._state["status"]["consecutive_failures"] = 0
                self._state["status"]["consecutive_successes"] = 0
                # Reset circuit breaker too
                for model_name in self._model_failures:
                    self._model_failures[model_name] = 0
        except ValueError:
            pass  # Ignore parse errors, keep current state

    def get_light_model(self) -> str:
        """
        Decide which small model to use for summarization.
        
        Priority order:
            1. Groq (fast, free) - skipped if circuit breaker is open
            2. Google Gemma (free, generous daily limit) - skipped if open
            3. Meta Muse Spark (paid, reliable fallback)
        
        If all three are exhausted or down, returns an empty string.
        """
        self._reset_daily_limits_if_needed()
        
        groq_remaining = self._state["models"]["groq_gpt_oss"]["tokens_remaining"]
        google_remaining = self._state["models"]["google_gemma"]["tokens_remaining"]
        muse_remaining = self._state["models"]["muse_spark"]["tokens_remaining"]

        # Circuit breaker: check if a model has failed too many times in a row
        groq_down = self._model_failures["groq_gpt_oss"] >= CIRCUIT_BREAKER_THRESHOLD
        google_down = self._model_failures["google_gemma"] >= CIRCUIT_BREAKER_THRESHOLD

        if groq_remaining > 10_000 and not groq_down:
            return "groq_gpt_oss"
        elif google_remaining > 50_000 and not google_down:
            if groq_down:
                print("   [Budget] Groq is down (circuit breaker). Switching to Google Gemma.")
            else:
                print("   [Budget] Groq is low. Switching to Google Gemma.")
            return "google_gemma"
        elif muse_remaining > 10_000:
            print("   [Budget] Both Groq and Google are unavailable. Switching to Meta Muse Spark (paid).")
            return "muse_spark"
        else:
            print("   [Budget] WARNING: All three models are exhausted or down. No AI summary will be generated.")
            return ""

    def record_usage(self, model_name: str, tokens_used: int, success: bool):
        """
        Record token usage and update status based on success/failure.
        
        Parameters
        ----------
        model_name : str
            "groq_gpt_oss", "google_gemma", or "muse_spark"
        tokens_used : int
            Approximate tokens consumed (input + output).
        success : bool
            Whether the API call succeeded.
        """
        if model_name not in self._state["models"]:
            return

        # Deduct tokens
        self._state["models"][model_name]["tokens_remaining"] -= tokens_used
        
        # Ensure we don't go below 0
        if self._state["models"][model_name]["tokens_remaining"] < 0:
            self._state["models"][model_name]["tokens_remaining"] = 0

        # Update success/failure streak
        if success:
            self._state["status"]["consecutive_successes"] += 1
            self._state["status"]["consecutive_failures"] = 0
            # Reset circuit breaker for this model
            self._model_failures[model_name] = 0
        else:
            self._state["status"]["consecutive_failures"] += 1
            self._state["status"]["consecutive_successes"] = 0
            # Increment circuit breaker counter
            self._model_failures[model_name] += 1
            if self._model_failures[model_name] >= CIRCUIT_BREAKER_THRESHOLD:
                print(f"   [Budget] ⚠️ Circuit breaker OPEN for {model_name} (failed {self._model_failures[model_name]} times). Skipping this model for the rest of the run.")

        self._save_state()

    def apply_dynamic_limits(self):
        """
        Adjust the daily max limits based on consecutive successes or failures.
        Called at the end of a successful or failed run.
        """
        successes = self._state["status"]["consecutive_successes"]
        failures = self._state["status"]["consecutive_failures"]

        if successes >= 3:
            print("   [Budget] 3+ consecutive successes. Applying +5% token bonus for next run.")
            for model in self._state["models"].values():
                model["max_daily_limit"] = int(model["max_daily_limit"] * BONUS_MULTIPLIER)
            self._state["status"]["consecutive_successes"] = 0  # Reset streak

        elif failures >= 2:
            print("   [Budget] 2+ consecutive failures. Applying -10% token penalty to be conservative.")
            for model in self._state["models"].values():
                model["max_daily_limit"] = int(model["max_daily_limit"] * PENALTY_MULTIPLIER)
            self._state["status"]["consecutive_failures"] = 0  # Reset streak

        self._save_state()
