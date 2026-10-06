"""Modular VLM planner wrapper."""

from __future__ import annotations
import time
from typing import Any, Dict
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import (
    BasePlanner,
    DirectAction,
    FailureEvent,
    FailureLayer,
    FailureSource,
    FailureStage,
    GoalCheckResult,
    PlanResult,
    PromptBundle,
)


class VLMPlanner(BasePlanner):
    """
    Modular wrapper for VLM inference.
    Delegates to the existing vlm_pipeline.vlm_planner.VLMPlanner
    but follows the BasePlanner interface.
    """

    def __init__(
        self,
        model_path: str,
        model_alias: str = "",
        device: str = "cuda",
        use_4bit: bool = False,
        quantization: str = "",
        trust_remote_code: bool = True
    ):
        from vlm_pipeline.vlm_planner import VLMPlanner as LegacyVLMPlanner
        self.model_alias = model_alias or model_path
        self.model_name = model_path
        self.loaded = False
        self.last_request_summary: Dict[str, Any] = {}
        self.legacy_planner = LegacyVLMPlanner(
            model_name=model_path,
            model_alias=self.model_alias,
            model_type="vlm",
            device=device,
            use_4bit=use_4bit,
            quantization=quantization,
        )
        self.parser = self.legacy_planner.parser
        self.legacy_planner.parser = self.parser

    def load_model(self) -> bool:
        if self.loaded:
            return True
        self.loaded = bool(self.legacy_planner.load_model())
        return self.loaded

    def _build_planning_failure_event(self, legacy_result) -> FailureEvent | None:
        if legacy_result.success:
            return None
        raw_output = legacy_result.raw_output or ""
        too_verbose = len(raw_output) >= 4000
        failure_id = FailureCode.PLANNER_OUTPUT_TOO_VERBOSE if too_verbose else FailureCode.PLANNER_OUTPUT_NOT_PARSEABLE
        message = legacy_result.error_message or "Planner output was not parseable as executable actions."
        if too_verbose and "too verbose" not in message:
            message = f"Previous planner output was too verbose ({len(raw_output)} characters) and not parseable. Reply with only a concise FINAL ACTIONS block."
        return FailureEvent(
            failure_id=failure_id,
            stage=FailureStage.BEFORE_EXECUTION,
            source=FailureSource.PARSER,
            action=None,
            evidence={
                "raw_output": raw_output,
                "raw_output_chars": len(raw_output),
                "model_type": "vlm",
            },
            failure_layer=FailureLayer.LAYER_1,
            should_replan=True,
            message=message,
        )

    def plan(self, bundle: PromptBundle) -> PlanResult:
        start_time = time.time()
        
        # 1. Prepare image for legacy planner
        # The legacy planner expects a single composite image or a List[Image]
        composite = None
        if bundle.images and len(bundle.images) > 0:
            composite = bundle.images[0]  # Assume first image is the composite
        metadata = dict(getattr(bundle, "metadata", {}) or {})
        max_new_tokens = int(metadata.get("max_new_tokens", 4096) or 4096)
        temperature = float(metadata.get("temperature", 0.0) or 0.0)
        use_vision = composite is not None
        # The format-repair regeneration is a second, hidden model call: off unless the
        # planner server was started with --format-repair, and never for prompt.version=v2.
        allow_format_repair = bool(metadata.get("allow_format_repair", False)) and metadata.get("prompt_version") != "v2"
        self.last_request_summary = {
            "model_type": "vlm",
            "text_only": not use_vision,
            "use_vision": use_vision,
            "image_present": use_vision,
            "image_shape": list(getattr(composite, "shape", ())) if composite is not None else [],
        }

        # 2. Call legacy planner
        # Note: Legacy planner uses its own state resolution internally if we give it env,
        # but we want to use the text we already built in the bundle.
        # We'll use a slightly modified call or direct inference if needed.
        
        # For now, we utilize the generate_plan method which takes system/user prompts
        if use_vision:
            self.legacy_planner.parser = self.parser
            legacy_result = self.legacy_planner.generate_plan(
                image=composite,
                system_prompt=bundle.system_prompt,
                user_prompt=bundle.user_prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                allow_format_repair=allow_format_repair,
            )
        else:
            self.legacy_planner.parser = self.parser
            legacy_result = self.legacy_planner.generate_plan_text_only(
                system_prompt=bundle.system_prompt,
                user_prompt=bundle.user_prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                allow_format_repair=allow_format_repair,
            )
        
        # 3. Map legacy ActionSkeleton to DirectAction
        actions = []
        if legacy_result.success:
            for skeleton in legacy_result.skeleton:
                if skeleton.action_name == "open-lid":
                    action_name = "open"
                elif skeleton.action_name == "close-lid":
                    action_name = "close"
                else:
                    action_name = skeleton.action_name
                actions.append(DirectAction(
                    action_name=action_name,
                    args=tuple(skeleton.args)
                ))
        
        return PlanResult(
            success=legacy_result.success,
            actions=actions,
            raw_output=legacy_result.raw_output,
            inference_time=time.time() - start_time,
            error_message=legacy_result.error_message,
            failure_event=self._build_planning_failure_event(legacy_result),
        )

    def _parse_goal_check_output(self, raw_output: str) -> GoalCheckResult:
        text = (raw_output or "").strip()
        normalized = text.upper()
        if normalized.startswith("GOAL_COMPLETE"):
            return GoalCheckResult(
                success=True,
                goal_satisfied=True,
                raw_output=raw_output,
                inference_time=0.0,
            )
        if normalized.startswith("GOAL_INCOMPLETE"):
            reason = text.split(":", 1)[1].strip() if ":" in text else "Goal is not complete."
            return GoalCheckResult(
                success=True,
                goal_satisfied=False,
                raw_output=raw_output,
                inference_time=0.0,
                reason=reason or "Goal is not complete.",
            )

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            cleaned = line.lstrip("-*0123456789. )").strip()
            upper_line = cleaned.upper()
            if "GOAL_INCOMPLETE" in upper_line:
                reason = cleaned.split(":", 1)[1].strip() if ":" in cleaned else "Goal is not complete."
                return GoalCheckResult(
                    success=True,
                    goal_satisfied=False,
                    raw_output=raw_output,
                    inference_time=0.0,
                    reason=reason or "Goal is not complete.",
                )
            if "GOAL_COMPLETE" in upper_line:
                return GoalCheckResult(
                    success=True,
                    goal_satisfied=True,
                    raw_output=raw_output,
                    inference_time=0.0,
                )

        return GoalCheckResult(
            success=False,
            goal_satisfied=False,
            raw_output=raw_output,
            inference_time=0.0,
            error_message="Goal check output must include GOAL_COMPLETE or GOAL_INCOMPLETE.",
        )

    def check_goal_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        icl_mode: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        held_object: str | None = None,
        image=None,
    ) -> GoalCheckResult:
        del icl_mode, held_object
        if not self.loaded:
            return GoalCheckResult(
                success=False,
                goal_satisfied=False,
                raw_output="",
                inference_time=0.0,
                error_message="Model not loaded. Call load_model() first.",
            )

        start_time = time.time()
        self.last_request_summary = {
            "model_type": "vlm",
            "request_type": "goal_check",
            "text_only": image is None,
            "use_vision": image is not None,
            "image_present": image is not None,
            "image_shape": list(getattr(image, "shape", ())) if image is not None else [],
        }
        try:
            if image is not None:
                raw_output = self.legacy_planner._generate_multimodal_output(
                    image=image,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                )
            else:
                raw_output = self.legacy_planner._generate_text_output(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                )
            result = self._parse_goal_check_output(raw_output)
            result.inference_time = time.time() - start_time
            return result
        except Exception as exc:
            return GoalCheckResult(
                success=False,
                goal_satisfied=False,
                raw_output="",
                inference_time=time.time() - start_time,
                error_message=str(exc),
            )

    def planner_settings(self) -> Dict[str, Any]:
        """Settings that change what the model generates (logged in trial_start)."""
        from llm_pipeline.planner import model_revision, thinking_mode_setting

        return {
            "planner": "local",
            "model_name": self.model_name,
            "model_alias": self.model_alias,
            "model_type": "vlm",
            "model_revision": model_revision(getattr(self.legacy_planner, "model", None)),
            "quantization": getattr(self.legacy_planner, "quantization", "none"),
            "thinking_mode": thinking_mode_setting(),
            "format_repair": False,       # local runs never request the format-repair call
        }

    def get_debug_info(self) -> Dict[str, Any]:
        return {
            "model_alias": self.model_alias,
            "model_name": self.model_name,
            "model_type": "vlm",
            "quantization": getattr(self.legacy_planner, "quantization", "none"),
            "loaded": self.loaded,
            "text_only": False,
            "use_vision": True,
            "last_request": dict(self.last_request_summary),
        }
