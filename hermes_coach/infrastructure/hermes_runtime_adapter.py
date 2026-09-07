"""The only place Coach talks to a model.

Requirement families: `HC-COMPANION`, `HC-PRIVACY`, `HC-PRODUCT`; sources
`SRC-001`, `SRC-026…029`, `SRC-070…075`, `SRC-092`, `SRC-096`.

Hermes is reached through its public constructor, not a fork: `AIAgent` already
accepts `enabled_toolsets`, `ephemeral_system_prompt`, `skip_memory` and
`skip_context_files`, which is exactly the seam the Phase 1 capability gate
required. No Coach branch is added to Hermes core.

Two boundaries matter here. Nothing Hermes-shaped escapes — callers get Coach
DTOs or a typed neutral failure. And nothing unvalidated escapes — provider text
is buffered, parsed and policy-checked before it can reach a sink, so rejected
content is never displayed, persisted or quoted back in an error.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from hermes_coach.contracts.runtime_contract import (
    CoachingStage,
    CoachOutput,
    RuntimeFailure,
    RuntimeFailureCode,
    RuntimeRequest,
    UsageAccounting,
    ValidatedRuntimeResult,
    stable_prompt_fingerprint,
)
from hermes_coach.prompt.question_validator import validate_question
from hermes_coach.prompt.system_prompt import COACH_SYSTEM_PROMPT


DEFAULT_MAX_REGENERATIONS = 2

# Attributes any of which, if non-empty, means the agent came back tool-capable.
_TOOL_ATTRIBUTES = ("tools", "tool_list", "available_tools")


class Agent(Protocol):
    """The slice of `AIAgent` the adapter uses."""

    def run(self, message: str) -> str: ...


AgentFactory = Callable[..., Any]


@dataclass(frozen=True)
class AdapterConfiguration:
    prompt_version: str
    provider: str
    model: str
    max_regenerations: int = DEFAULT_MAX_REGENERATIONS


class RuntimeRejected(RuntimeError):
    """A turn produced no deliverable output.

    Carries a typed `RuntimeFailure` and a correlation id. The message is safe
    by construction: it never contains the prompt, provider text or a secret.
    """

    def __init__(self, failure: RuntimeFailure, correlation_id: str) -> None:
        super().__init__(f"{failure.code}: {failure.safe_message} [{correlation_id}]")
        self.failure = failure
        self.correlation_id = correlation_id


# Stated on every turn, because the model is otherwise guessing. A live Haiku
# turn answered `{"stage", "question", "rationale"}` against a model whose
# field is `coaching_stage` and whose config is `extra="forbid"` - three ways
# wrong, none of them the model's fault.
# One candidate, spelled out. A field name the model has to guess is a field it
# gets wrong, and a candidate that fails validation costs a whole regeneration.
# This exact object is asserted to validate against `CandidateRecord`.
CANDIDATE_EXAMPLE = (
    '{"candidate_id": "c1", "kind": "goal", '
    '"value": "Den 30/06 co mot san pham chay duoc cho nguoi dung that", '
    '"source_turn_id": "turn-1"}'
)

OUTPUT_CONTRACT = (
    "[output]\n"
    "Tra ve dung mot doi tuong JSON, khong rao markdown, khong van xuoi kem theo.\n"
    'Bat buoc: "question" (mot cau hoi, dung mot dau ?) va "coaching_stage" '
    "(mot trong: " + ", ".join(stage.value for stage in CoachingStage) + ").\n"
    "Khong them khoa nao ngoai schema - extra keys bi tu choi.\n"
    "[records]\n"
    "Mot phien khong luu lai gi thi khong con la coaching. Khi Coachee tu noi ra "
    "mot trong nhung dieu duoi day, dat no vao mang tuong ung; mang nao khong co "
    "gi thi bo han, khong gui mang rong:\n"
    "- candidate_goals: muc tieu chinh Coachee dat ra cho minh.\n"
    "- candidate_insights: dieu Coachee tu nhan ra ve chinh minh.\n"
    "- candidate_commitments: hanh dong cu the Coachee noi se lam.\n"
    "- candidate_memories: dieu ve Coachee dang nho cho nhung phien sau.\n"
    "Moi phan tu dung dung dang nay: " + CANDIDATE_EXAMPLE + "\n"
    '"kind" phai trung ten mang. "value" la loi cua Coachee, khong phai loi khuyen '
    'cua ban va khong phai cau hoi cua ban. "source_turn_id" lay tu "turn" o '
    "[coach_context]. Khong them khoa nao khac vao phan tu.\n"
    "Chi de xuat cai vua xuat hien trong luot nay, toi da mot phan tu moi mang. "
    "Day la de nghi de Coachee xac nhan tung cai mot, khong phai ban ghi da chot.\n"
    # The model re-proposed the same thought on nearly every turn because it had
    # no way to know it had already proposed it. `already_proposed` in
    # [coach_context] is that missing half; this sentence is what makes the model
    # read it. Exact duplicates are dropped by the server regardless, but the
    # model paraphrases, and no string comparison catches a paraphrase.
    "Trong [coach_context] co already_proposed: nhung dieu phien nay da de xuat "
    "roi. Khong de xuat lai bat cu dieu nao trong do, ke ca khi dien dat khac di "
    "hay Coachee nhac lai. Chi de xuat khi that su moi.\n"
    # One session produced records reading "Tôi coi trọng…" beside "Bạn bỏ một
    # khoá học…". These are the Coachee's own words about themselves, read back
    # months later; a record that switches person reads like someone else wrote
    # it, which is exactly what the product must not feel like.
    # The six-step structure rested entirely on the closing gate, with nothing
    # checking a step had any content — a live run had the Coach move to Reality
    # and immediately ask an Options question, and nothing objected. This is
    # where the content comes from. Reported to the Coachee for now rather than
    # enforced; enforcing on fields nobody has ever produced would stop every
    # step closing.
    "[stage_snapshot]\n"
    "Them khoa \"stage_snapshot\": mot object ghi lai nhung gi Coachee DA NOI ve "
    "buoc hien tai. Chi ghi dieu Coachee tu noi; khong suy dien, khong dien ho, "
    "khong dat gia tri gia de cho du field.\n"
    "- pre_coaching: ready, coaching_understood, roles_agreed, boundaries_agreed "
    "(true/false)\n"
    "- goal: title, why_it_matters, success_evidence, target_date\n"
    "- reality: facts, present_state, gap\n"
    "- options: options (mang cac lua chon Coachee tu nghi ra), chosen\n"
    "- will: chosen_action, due_at, commitment_score (1-10)\n"
    "- review: takeaway\n"
    "Chua noi toi thi bo khoa do han. De trong con dung hon la dien bua.\n"
    '"value" luon viet o ngoi thu nhat, nhu chinh Coachee tu noi ve minh: '
    '"Toi hay bo do du an giua chung", khong phai "Ban hay bo do" hay '
    '"Coachee hay bo do". Day la ban ghi cua ho, khong phai ghi chu ve ho.'
)


def _unfenced(raw: str) -> str:
    """Return the JSON object inside a reply, fence or no fence.

    A text model wraps JSON in ```json by habit. Rejecting that would
    spend every regeneration on formatting rather than on coaching. This narrows
    to the outermost braces only, so a fenced object parses and a payload that is
    not JSON stays exactly as invalid as it was.
    """
    opening = raw.find("{")
    closing = raw.rfind("}")
    if opening == -1 or closing <= opening:
        return raw
    return raw[opening : closing + 1]


@dataclass
class _UsageTally:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, sent: str, received: str) -> None:
        # Whitespace tokens are a stand-in until a provider reports real usage;
        # what matters to the contract is that retries are counted, not skipped.
        self.input_tokens += len(sent.split())
        self.output_tokens += len(received.split())

    def snapshot(self) -> UsageAccounting:
        return UsageAccounting(
            input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )


class CoachRuntimeAdapter:
    """One long-lived agent per Coach session, behind a Coach-only interface."""

    def __init__(
        self,
        configuration: AdapterConfiguration,
        *,
        agent_factory: AgentFactory,
    ) -> None:
        self._configuration = configuration
        self._agent_factory = agent_factory
        self._agents: dict[str, Any] = {}
        self._prompt = COACH_SYSTEM_PROMPT
        self._prompt_hash = stable_prompt_fingerprint(self._prompt)

    def generate(
        self,
        request: RuntimeRequest,
        *,
        sink: Callable[[CoachOutput], None] | None = None,
    ) -> ValidatedRuntimeResult:
        correlation_id = str(uuid.uuid4())
        usage = _UsageTally()

        # Checked before the agent exists: a drifted cache prefix must not cost
        # a provider call.
        self._require_stable_prompt(request, correlation_id, usage)

        agent = self._agent_for(request.session_id, correlation_id, usage)
        turn_message = self._compose_turn(request)

        reasons: tuple[str, ...] = ()
        last_code: RuntimeFailureCode = "schema_error"
        attempts = 0

        while attempts <= self._configuration.max_regenerations:
            attempts += 1
            message = (
                turn_message if attempts == 1 else self._retry_message(turn_message, reasons)
            )
            try:
                raw = agent.run(message)
            except Exception as error:  # provider transport, not our contract
                raise self._fail(
                    "provider_error",
                    "Không gọi được nhà cung cấp mô hình. Vui lòng thử lại.",
                    attempts,
                    usage,
                    correlation_id,
                    retryable=True,
                ) from _WithoutDetail(error)

            usage.add(message, raw)

            try:
                output = CoachOutput.model_validate_json(_unfenced(raw))
            except ValidationError:
                last_code = "schema_error"
                reasons = ("schema_invalid",)
                continue

            verdict = validate_question(
                output.question, grounded_coachee_input=request.user_message
            )
            if verdict.valid:
                if sink is not None:
                    sink(output)
                return ValidatedRuntimeResult(
                    output=output, attempts=attempts, usage=usage.snapshot()
                )

            last_code = "policy_error"
            reasons = tuple(code.value for code in verdict.reason_codes)

        raise self._fail(
            last_code,
            self._safe_message_for(last_code),
            attempts,
            usage,
            correlation_id,
            retryable=True,
        )

    def _require_stable_prompt(
        self, request: RuntimeRequest, correlation_id: str, usage: _UsageTally
    ) -> None:
        if (
            request.prompt_version != self._configuration.prompt_version
            or request.system_prompt_hash != self._prompt_hash
        ):
            raise self._fail(
                "prompt_changed",
                "Phiên bản prompt đã thay đổi; hãy bắt đầu phiên mới.",
                0,
                usage,
                correlation_id,
                retryable=False,
            )

    def _agent_for(
        self, session_id: str, correlation_id: str, usage: _UsageTally
    ) -> Any:
        """One agent per session, so the cached prompt prefix stays warm."""
        agent = self._agents.get(session_id)
        if agent is None:
            agent = self._agent_factory(
                provider=self._configuration.provider,
                model=self._configuration.model,
                ephemeral_system_prompt=self._prompt,
                enabled_toolsets=[],
                skip_memory=True,
                skip_context_files=True,
                load_soul_identity=False,
                save_trajectories=False,
                quiet_mode=True,
            )
            self._require_no_tools(agent, correlation_id, usage)
            self._agents[session_id] = agent
        return agent

    def _require_no_tools(
        self, agent: Any, correlation_id: str, usage: _UsageTally
    ) -> None:
        """Declaring no toolsets is not proof; check what was actually built."""
        for attribute in _TOOL_ATTRIBUTES:
            if getattr(agent, attribute, None):
                raise self._fail(
                    "provider_error",
                    "Runtime trả về agent có tool; Coach yêu cầu không có tool.",
                    0,
                    usage,
                    correlation_id,
                    retryable=False,
                )

    def _compose_turn(self, request: RuntimeRequest) -> str:
        """Dynamic state rides in the turn; the system prompt never changes.

        The output contract is stated here rather than in the system prompt,
        which is fingerprinted and must stay byte-stable.
        """
        context = "\n".join(
            f"{key}: {value}" for key, value in sorted(request.structured_context.items())
        )
        # The turn id travels with the turn because a candidate has to name the
        # turn it came from, and the model has no other way to know it.
        return (
            f"[coach_context]\nstage: {request.current_stage.value}\n"
            f"turn: {request.turn_id}\n{context}\n"
            f"[coachee]\n{request.user_message}\n{OUTPUT_CONTRACT}"
        )

    @staticmethod
    def _retry_message(turn_message: str, reasons: tuple[str, ...]) -> str:
        """A retry restates the same turn.

        It is appended to the same conversation as another attempt at this turn,
        never as a fabricated Coachee message, so role alternation holds.
        """
        return f"{turn_message}\n[regenerate]\nrejected: {', '.join(reasons)}"

    @staticmethod
    def _safe_message_for(code: RuntimeFailureCode) -> str:
        if code == "policy_error":
            return "Câu hỏi sinh ra không đạt chuẩn Coach sau số lần thử cho phép."
        return "Kết quả mô hình không đúng schema sau số lần thử cho phép."

    @staticmethod
    def _fail(
        code: RuntimeFailureCode,
        safe_message: str,
        attempts: int,
        usage: _UsageTally,
        correlation_id: str,
        *,
        retryable: bool,
    ) -> RuntimeRejected:
        return RuntimeRejected(
            RuntimeFailure(
                code=code,
                retryable=retryable,
                safe_message=safe_message,
                attempts=attempts,
                usage=usage.snapshot(),
            ),
            correlation_id,
        )


class _WithoutDetail(Exception):
    """Chains a provider error without letting its text into the message.

    A provider exception routinely carries the URL and sometimes the key. It is
    kept as `__cause__` for local debugging and never rendered.
    """

    def __init__(self, original: BaseException) -> None:
        super().__init__(type(original).__name__)
        self.original_type = type(original).__name__
