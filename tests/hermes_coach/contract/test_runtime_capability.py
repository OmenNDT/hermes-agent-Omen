from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

import pytest
from pydantic import ValidationError

from hermes_coach.contracts.egress_contract import (
    EgressAuthorization,
    EgressCategory,
    EgressConsentAction,
    EgressConsentAuthority,
    EgressConsentDecision,
    EgressItemRef,
    EgressManifest,
    EgressRequirement,
    ProviderRetentionDisclosure,
    ProviderRetentionStatus,
)
from hermes_coach.contracts.runtime_contract import (
    CoachOutput,
    CoachingStage,
    PromptStabilityError,
    RuntimeCapabilities,
    RuntimeRequest,
    GateEvidence,
    GateAnswer,
    GoalSmartAssessment,
    GoalSmartStatus,
    GoalValueStatus,
    RuntimeFailure,
    ValidatedRuntimeResult,
    assert_prompt_stable,
    stable_prompt_fingerprint,
)
from hermes_coach.contracts.transition_contract import TransitionDecision
from tests.hermes_coach.evals.runtime_harness import BufferedRuntimeHarness


ROOT = Path(__file__).parents[3]


def _agent_init_parameters() -> set[str]:
    tree = ast.parse((ROOT / "run_agent.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AIAgent":
            init = next(
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == "__init__"
            )
            return {argument.arg for argument in init.args.args}
    raise AssertionError("AIAgent.__init__ not found")


def test_existing_hermes_runtime_exposes_required_isolation_controls() -> None:
    assert {
        "enabled_toolsets",
        "session_db",
        "skip_context_files",
        "skip_memory",
    } <= _agent_init_parameters()


def test_coach_runtime_capabilities_are_narrow_and_buffered() -> None:
    capabilities = RuntimeCapabilities()

    assert capabilities.supports_tools is False
    assert capabilities.uses_hermes_memory is False
    assert capabilities.uses_context_files is False
    assert capabilities.uses_hermes_session_db is False
    assert capabilities.buffers_before_validation is True
    assert capabilities.structured_output is True


def test_runtime_request_binds_every_turn_to_a_stable_system_prompt() -> None:
    prompt_hash = stable_prompt_fingerprint("immutable coach prompt")
    request = RuntimeRequest(
        session_id="session-1",
        turn_id="turn-1",
        prompt_version="coach-v1",
        system_prompt_hash=prompt_hash,
        current_stage=CoachingStage.GOAL,
        user_message="Tôi muốn phát triển sự nghiệp.",
        structured_context={"goal_status": "candidate"},
    )

    assert request.system_prompt_hash == prompt_hash
    assert_prompt_stable(prompt_hash, prompt_hash)
    with pytest.raises(PromptStabilityError):
        assert_prompt_stable(prompt_hash, stable_prompt_fingerprint("mutated"))


def test_output_contract_allows_exactly_one_question_field() -> None:
    output = CoachOutput(
        question="Điều gì sẽ khác đi khi mục tiêu này được hoàn thành?",
        coaching_stage=CoachingStage.GOAL,
    )

    assert output.question.endswith("?")
    with pytest.raises(ValidationError):
        CoachOutput.model_validate(
            {
                "question": "Bạn muốn tập trung vào điều gì?",
                "questions": ["Khi nào?"],
                "coaching_stage": "goal",
            }
        )


def test_output_cannot_claim_complete_smart_status_without_all_components() -> None:
    with pytest.raises(ValidationError):
        CoachOutput(
            question="Mục tiêu này đã có thời hạn cụ thể chưa?",
            coaching_stage=CoachingStage.GOAL,
            goal_smart_status=GoalSmartStatus.COMPLETE,
        )


def test_forward_transition_requires_bound_explicit_yes_evidence() -> None:
    evidence = GateEvidence(
        stage=CoachingStage.GOAL,
        closing_question_turn_id="turn-question",
        response_turn_id="turn-response",
        exact_response="Yes, mục tiêu này đã đúng.",
        answer=GateAnswer.YES,
    )

    transition = TransitionDecision(
        current_stage=CoachingStage.GOAL,
        next_stage=CoachingStage.REALITY,
        gate_evidence=evidence,
        stage_state_complete=True,
        confirmed_stages=(CoachingStage.PRE_COACHING,),
        goal_smart_status=GoalSmartStatus.COMPLETE,
        goal_smart_assessment=GoalSmartAssessment(
            specific=True,
            measurable=True,
            achievable=True,
            relevant=True,
            time_bound=True,
        ),
        goal_value_status=GoalValueStatus.CONFIRMED,
        goal_influence_confirmed=True,
    )
    assert transition.next_stage is CoachingStage.REALITY

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.OPTIONS,
            gate_evidence=evidence,
            stage_state_complete=True,
            confirmed_stages=(CoachingStage.PRE_COACHING,),
            goal_smart_status=GoalSmartStatus.COMPLETE,
            goal_smart_assessment=GoalSmartAssessment(
                specific=True,
                measurable=True,
                achievable=True,
                relevant=True,
                time_bound=True,
            ),
            goal_value_status=GoalValueStatus.CONFIRMED,
            goal_influence_confirmed=True,
        )


def test_no_or_unclear_gate_cannot_advance() -> None:
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.REALITY,
            next_stage=CoachingStage.OPTIONS,
            gate_evidence=GateEvidence(
                stage=CoachingStage.REALITY,
                closing_question_turn_id="turn-question",
                response_turn_id="turn-response",
                exact_response="Chưa rõ.",
                answer=GateAnswer.UNCLEAR,
            ),
            stage_state_complete=True,
            confirmed_stages=(CoachingStage.PRE_COACHING, CoachingStage.GOAL),
        )


def test_goal_yes_cannot_advance_until_all_goal_predicates_are_complete() -> None:
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.REALITY,
            stage_state_complete=True,
            confirmed_stages=(CoachingStage.PRE_COACHING,),
            gate_evidence=GateEvidence(
                stage=CoachingStage.GOAL,
                closing_question_turn_id="turn-question",
                response_turn_id="turn-response",
                exact_response="Yes",
                answer=GateAnswer.YES,
            ),
        )


def test_goal_cannot_claim_smart_when_a_component_is_missing() -> None:
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.REALITY,
            stage_state_complete=True,
            confirmed_stages=(CoachingStage.PRE_COACHING,),
            goal_smart_status=GoalSmartStatus.COMPLETE,
            goal_smart_assessment=GoalSmartAssessment(
                specific=True,
                measurable=True,
                achievable=True,
                relevant=True,
                time_bound=False,
            ),
            goal_value_status=GoalValueStatus.CONFIRMED,
            goal_influence_confirmed=True,
            gate_evidence=GateEvidence(
                stage=CoachingStage.GOAL,
                closing_question_turn_id="turn-question",
                response_turn_id="turn-response",
                exact_response="Yes",
                answer=GateAnswer.YES,
            ),
        )


def test_will_requires_commitment_score_from_one_to_ten() -> None:
    evidence = GateEvidence(
        stage=CoachingStage.WILL,
        closing_question_turn_id="turn-question",
        response_turn_id="turn-response",
        exact_response="Yes",
        answer=GateAnswer.YES,
    )
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.WILL,
            next_stage=CoachingStage.REVIEW,
            stage_state_complete=True,
            confirmed_stages=(
                CoachingStage.PRE_COACHING,
                CoachingStage.GOAL,
                CoachingStage.REALITY,
                CoachingStage.OPTIONS,
            ),
            gate_evidence=evidence,
        )

    transition = TransitionDecision(
        current_stage=CoachingStage.WILL,
        next_stage=CoachingStage.REVIEW,
        stage_state_complete=True,
        confirmed_stages=(
            CoachingStage.PRE_COACHING,
            CoachingStage.GOAL,
            CoachingStage.REALITY,
            CoachingStage.OPTIONS,
        ),
        will_commitment_score=7,
        gate_evidence=evidence,
    )
    assert transition.will_commitment_score == 7


def test_rollback_targets_only_an_earlier_grow_stage() -> None:
    transition = TransitionDecision(
        current_stage=CoachingStage.WILL,
        next_stage=CoachingStage.REALITY,
        rollback_to=CoachingStage.REALITY,
        confirmed_stages=(CoachingStage.PRE_COACHING, CoachingStage.GOAL),
    )
    assert transition.rollback_to is CoachingStage.REALITY

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.WILL,
            next_stage=CoachingStage.REALITY,
            rollback_to=CoachingStage.REALITY,
            confirmed_stages=(
                CoachingStage.PRE_COACHING,
                CoachingStage.GOAL,
                CoachingStage.REALITY,
                CoachingStage.OPTIONS,
            ),
            options_novelty_confirmed=True,
            will_commitment_score=8,
        )

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.WILL,
            next_stage=CoachingStage.PRE_COACHING,
            rollback_to=CoachingStage.PRE_COACHING,
        )


def test_readiness_reset_is_the_only_return_path_to_pre_coaching() -> None:
    transition = TransitionDecision(
        current_stage=CoachingStage.GOAL,
        next_stage=CoachingStage.PRE_COACHING,
        return_to_pre_coaching=True,
    )
    assert transition.next_stage is CoachingStage.PRE_COACHING

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.PRE_COACHING,
        )

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.PRE_COACHING,
            return_to_pre_coaching=True,
            confirmed_stages=(CoachingStage.PRE_COACHING,),
            stage_state_complete=True,
        )

    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.GOAL,
            next_stage=CoachingStage.PRE_COACHING,
            return_to_pre_coaching=True,
            goal_smart_assessment=GoalSmartAssessment(specific=True),
        )


def test_rollback_to_goal_rejects_partial_smart_state() -> None:
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.OPTIONS,
            next_stage=CoachingStage.GOAL,
            rollback_to=CoachingStage.GOAL,
            confirmed_stages=(CoachingStage.PRE_COACHING,),
            goal_smart_assessment=GoalSmartAssessment(specific=True),
        )


def test_negated_or_qualified_yes_does_not_open_gate() -> None:
    with pytest.raises(ValidationError):
        TransitionDecision(
            current_stage=CoachingStage.PRE_COACHING,
            next_stage=CoachingStage.GOAL,
            stage_state_complete=True,
            gate_evidence=GateEvidence(
                stage=CoachingStage.PRE_COACHING,
                closing_question_turn_id="turn-question",
                response_turn_id="turn-response",
                exact_response="No, not yes.",
                answer=GateAnswer.YES,
            ),
        )


def test_egress_manifest_contains_metadata_but_never_payload_or_secrets() -> None:
    forbidden = {"api_key", "content", "payload", "prompt", "secret", "transcript"}
    assert forbidden.isdisjoint(EgressManifest.model_fields)
    assert EgressManifest.model_fields["requirement"].annotation is EgressRequirement


class _Response:
    def __init__(self, raw_output: dict, input_tokens: int = 10, output_tokens: int = 5):
        self.raw_output = raw_output
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeProvider:
    def __init__(self, responses: list[_Response]):
        self.responses = responses
        self.calls: list[dict] = []

    def complete(self, request, *, capabilities, validation_reason):
        self.calls.append(
            {
                "request": request,
                "capabilities": capabilities,
                "validation_reason": validation_reason,
            }
        )
        return self.responses[len(self.calls) - 1]


def _runtime_request(prompt_hash: str) -> RuntimeRequest:
    return RuntimeRequest(
        session_id="session-1",
        turn_id="turn-1",
        prompt_version="coach-v1",
        system_prompt_hash=prompt_hash,
        current_stage=CoachingStage.GOAL,
        user_message="Tôi muốn làm rõ mục tiêu.",
    )


def _egress_context(
) -> tuple[EgressManifest, EgressConsentAuthority, EgressAuthorization]:
    manifest = EgressManifest(
        manifest_id="manifest-1",
        profile_id="profile-1",
        session_id="session-1",
        turn_id="turn-1",
        created_at=datetime.now(UTC),
        provider="fake-provider",
        model="fake-model",
        purpose="Generate one coaching question",
        requirement=EgressRequirement.REQUIRED,
        categories=(EgressCategory.CURRENT_TURN,),
        item_refs=(
            EgressItemRef(
                local_id="turn-1",
                category=EgressCategory.CURRENT_TURN,
                requirement=EgressRequirement.REQUIRED,
            ),
        ),
        consent_scope="model-egress:current-turn",
        consent_version="v1",
        provider_retention=ProviderRetentionDisclosure(
            status=ProviderRetentionStatus.UNKNOWN,
            label="unknown",
            version="v1",
        ),
    )
    consent = EgressConsentDecision(
        profile_id=manifest.profile_id,
        session_id=manifest.session_id,
        scope=manifest.consent_scope,
        version=manifest.consent_version,
        action=EgressConsentAction.CONFIRM,
        ui_event_id="ui-event-1",
        created_at=datetime.now(UTC),
        allows_new_requests=True,
    )
    authority = EgressConsentAuthority()
    authority.record_ui_decision(consent)
    authorization = authority.issue_authorization(
        profile_id=manifest.profile_id,
        ui_event_id=consent.ui_event_id,
        manifest_id=manifest.manifest_id,
        session_id=manifest.session_id,
        turn_id=manifest.turn_id,
        scope=manifest.consent_scope,
        version=manifest.consent_version,
    )
    return manifest, authority, authorization


def test_runtime_buffers_invalid_output_and_regenerates_before_returning() -> None:
    manifest, authority, authorization = _egress_context()
    harness = BufferedRuntimeHarness(
        "stable prompt", authority, max_regenerations=1
    )
    provider = _FakeProvider(
        [
            _Response({"question": "Bạn nên viết mục tiêu ngay."}),
            _Response(
                {
                    "question": "Kết quả cụ thể nào sẽ cho bạn biết mình đã đạt mục tiêu?",
                    "coaching_stage": "goal",
                }
            ),
        ]
    )

    accepted = []
    result = harness.run(
        provider,
        _runtime_request(harness.system_prompt_hash),
        lambda _: None,
        manifest,
        authorization,
        accepted.append,
    )

    assert isinstance(result, ValidatedRuntimeResult)
    assert result.attempts == 2
    assert result.usage.input_tokens == 20
    assert provider.calls[0]["capabilities"].supports_tools is False
    assert provider.calls[1]["validation_reason"].startswith("schema_error")
    assert accepted == [result]
    assert accepted[0].output.question.startswith("Kết quả cụ thể")


def test_runtime_fails_closed_after_bounded_semantic_retries() -> None:
    manifest, authority, authorization = _egress_context()
    harness = BufferedRuntimeHarness(
        "stable prompt", authority, max_regenerations=1
    )
    provider = _FakeProvider(
        [
            _Response({"question": "Bạn có nên làm ngay?", "coaching_stage": "will"}),
            _Response({"question": "Bạn phải làm ngay chứ?", "coaching_stage": "will"}),
        ]
    )

    accepted = []
    result = harness.run(
        provider,
        _runtime_request(harness.system_prompt_hash),
        lambda _: "disguised_advice",
        manifest,
        authorization,
        accepted.append,
    )

    assert isinstance(result, RuntimeFailure)
    assert result.code == "policy_error"
    assert result.attempts == 2
    assert result.usage.output_tokens == 10
    assert not hasattr(result, "raw_output")
    assert accepted == []


def test_runtime_fails_closed_when_semantic_validator_raises() -> None:
    manifest, authority, authorization = _egress_context()
    harness = BufferedRuntimeHarness("stable prompt", authority)
    provider = _FakeProvider(
        [_Response({"question": "Bạn muốn tập trung vào điều gì?", "coaching_stage": "goal"})]
    )

    def broken_validator(_):
        raise RuntimeError("validator unavailable")

    result = harness.run(
        provider,
        _runtime_request(harness.system_prompt_hash),
        broken_validator,
        manifest,
        authorization,
    )

    assert isinstance(result, RuntimeFailure)
    assert result.code == "policy_error"
    assert result.retryable is False


def test_runtime_does_not_call_provider_after_egress_consent_withdrawal() -> None:
    manifest, authority, authorization = _egress_context()
    authority.record_ui_decision(
        EgressConsentDecision(
            profile_id=manifest.profile_id,
            session_id=manifest.session_id,
            scope=manifest.consent_scope,
            version=manifest.consent_version,
            action=EgressConsentAction.WITHDRAW,
            ui_event_id="ui-event-withdrawal",
            created_at=datetime.now(UTC),
            allows_new_requests=False,
        )
    )
    harness = BufferedRuntimeHarness("stable prompt", authority)
    provider = _FakeProvider(
        [_Response({"question": "Bạn muốn tập trung vào điều gì?", "coaching_stage": "goal"})]
    )
    result = harness.run(
        provider,
        _runtime_request(harness.system_prompt_hash),
        lambda _: None,
        manifest,
        authorization,
    )

    assert isinstance(result, RuntimeFailure)
    assert result.code == "consent_error"
    assert result.attempts == 0
    assert provider.calls == []


def test_runtime_rejects_forged_egress_authorization_before_provider_call() -> None:
    manifest, authority, _ = _egress_context()
    harness = BufferedRuntimeHarness("stable prompt", authority)
    provider = _FakeProvider(
        [_Response({"question": "Bạn muốn tập trung vào điều gì?", "coaching_stage": "goal"})]
    )
    forged = EgressAuthorization(
        authorization_token="x" * 32,
        ui_event_id="forged-ui-event",
        manifest_id=manifest.manifest_id,
        session_id=manifest.session_id,
        turn_id=manifest.turn_id,
        scope=manifest.consent_scope,
        version=manifest.consent_version,
    )

    result = harness.run(
        provider,
        _runtime_request(harness.system_prompt_hash),
        lambda _: None,
        manifest,
        forged,
    )

    assert isinstance(result, RuntimeFailure)
    assert result.code == "consent_error"
    assert provider.calls == []


def test_provider_call_admission_is_atomic_with_consent_withdrawal() -> None:
    manifest, authority, authorization = _egress_context()
    withdrawal_started = Event()
    withdrawal_finished = Event()

    def withdraw() -> None:
        withdrawal_started.set()
        authority.record_ui_decision(
            EgressConsentDecision(
                profile_id=manifest.profile_id,
                session_id=manifest.session_id,
                scope=manifest.consent_scope,
                version=manifest.consent_version,
                action=EgressConsentAction.WITHDRAW,
                ui_event_id="ui-event-racing-withdrawal",
                created_at=datetime.now(UTC),
                allows_new_requests=False,
            )
        )
        withdrawal_finished.set()

    with authority.provider_call_lease(
        authorization,
        profile_id=manifest.profile_id,
        manifest_id=manifest.manifest_id,
        session_id=manifest.session_id,
        turn_id=manifest.turn_id,
        scope=manifest.consent_scope,
        version=manifest.consent_version,
    ) as admitted:
        assert admitted is True
        withdrawal_thread = Thread(target=withdraw)
        withdrawal_thread.start()
        assert withdrawal_started.wait(timeout=1)
        assert not withdrawal_finished.wait(timeout=0.05)

    assert withdrawal_finished.wait(timeout=1)
    withdrawal_thread.join(timeout=1)
    assert not withdrawal_thread.is_alive()
    assert authority.permits(
        authorization,
        profile_id=manifest.profile_id,
        manifest_id=manifest.manifest_id,
        session_id=manifest.session_id,
        turn_id=manifest.turn_id,
        scope=manifest.consent_scope,
        version=manifest.consent_version,
    ) is False
