from __future__ import annotations

from typing import Any, Callable, Protocol

from pydantic import ValidationError

from hermes_coach.contracts.egress_contract import (
    EgressAuthorization,
    EgressConsentAuthority,
    EgressManifest,
)
from hermes_coach.contracts.runtime_contract import (
    COACH_RUNTIME_CAPABILITIES,
    CoachOutput,
    RuntimeFailure,
    RuntimeFailureCode,
    RuntimeRequest,
    UsageAccounting,
    ValidatedRuntimeResult,
    assert_prompt_stable,
    stable_prompt_fingerprint,
)


class ProviderResponse(Protocol):
    raw_output: dict[str, Any]
    input_tokens: int
    output_tokens: int


class StructuredProvider(Protocol):
    def complete(
        self,
        request: RuntimeRequest,
        *,
        capabilities: object,
        validation_reason: str | None,
    ) -> ProviderResponse: ...


SemanticValidator = Callable[[CoachOutput], str | None]


class BufferedRuntimeHarness:
    """Phase-1 provider seam; raw output never leaves the validation loop."""

    def __init__(
        self,
        system_prompt: str,
        consent_authority: EgressConsentAuthority,
        max_regenerations: int = 1,
    ) -> None:
        if max_regenerations < 0:
            raise ValueError("max_regenerations cannot be negative")
        self.system_prompt_hash = stable_prompt_fingerprint(system_prompt)
        self.consent_authority = consent_authority
        self.max_regenerations = max_regenerations

    def run(
        self,
        provider: StructuredProvider,
        request: RuntimeRequest,
        semantic_validator: SemanticValidator,
        egress_manifest: EgressManifest,
        authorization: EgressAuthorization,
        accepted_sink: Callable[[ValidatedRuntimeResult], None] | None = None,
    ) -> ValidatedRuntimeResult | RuntimeFailure:
        usage = UsageAccounting(input_tokens=0, output_tokens=0)
        reason: str | None = None
        if not self._manifest_matches_request(request, egress_manifest):
            return self._failure("consent_error", False, 0, usage)
        try:
            assert_prompt_stable(self.system_prompt_hash, request.system_prompt_hash)
        except RuntimeError:
            return self._failure("prompt_changed", False, 0, usage)

        for attempt in range(1, self.max_regenerations + 2):
            with self.consent_authority.provider_call_lease(
                authorization,
                profile_id=egress_manifest.profile_id,
                manifest_id=egress_manifest.manifest_id,
                session_id=request.session_id,
                turn_id=request.turn_id,
                scope=egress_manifest.consent_scope,
                version=egress_manifest.consent_version,
            ) as admitted:
                if not admitted:
                    return self._failure("consent_error", False, attempt - 1, usage)
                try:
                    response = provider.complete(
                        request,
                        capabilities=COACH_RUNTIME_CAPABILITIES,
                        validation_reason=reason,
                    )
                    usage = UsageAccounting(
                        input_tokens=usage.input_tokens + response.input_tokens,
                        output_tokens=usage.output_tokens + response.output_tokens,
                    )
                    output = CoachOutput.model_validate(response.raw_output)
                except ValidationError as exc:
                    reason = f"schema_error:{exc.error_count()}"
                    continue
                except Exception:
                    return self._failure("provider_error", True, attempt, usage)

                try:
                    reason = semantic_validator(output)
                except Exception:
                    return self._failure("policy_error", False, attempt, usage)
                if reason is None:
                    result = ValidatedRuntimeResult(output=output, attempts=attempt, usage=usage)
                    if accepted_sink is not None:
                        accepted_sink(result)
                    return result

        code: RuntimeFailureCode = (
            "policy_error" if reason and not reason.startswith("schema_error") else "schema_error"
        )
        return self._failure(code, True, self.max_regenerations + 1, usage)

    @staticmethod
    def _manifest_matches_request(
        request: RuntimeRequest,
        manifest: EgressManifest,
    ) -> bool:
        return bool(
            manifest.session_id == request.session_id
            and manifest.turn_id == request.turn_id
        )

    @staticmethod
    def _failure(
        code: RuntimeFailureCode,
        retryable: bool,
        attempts: int,
        usage: UsageAccounting,
    ) -> RuntimeFailure:
        return RuntimeFailure(
            code=code,
            retryable=retryable,
            safe_message="Không thể tạo câu hỏi hợp lệ lúc này. Bạn có muốn thử lại?",
            attempts=attempts,
            usage=usage,
        )
