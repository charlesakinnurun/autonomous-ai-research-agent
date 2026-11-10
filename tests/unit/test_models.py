"""Contract tests for Pydantic models and state reducers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from research_agent.models import (
    ApprovalKind,
    ApprovalRequest,
    ApprovalStatus,
    Architecture,
    BudgetLimits,
    BudgetState,
    Chunk,
    Citation,
    Claim,
    ClaimBundle,
    ClaimEvidence,
    ClaimVerdict,
    CoverageGap,
    CoverageReport,
    CritiqueDecision,
    Document,
    DocumentMetadata,
    EvidenceSpan,
    FinalReport,
    ReportDraft,
    ReportSection,
    ResearchPlan,
    ResearchState,
    RunContext,
    Source,
    SourceProvenance,
    SubQuestion,
    TokenUsage,
    UsageLedger,
    Verdict,
    append_unique_by_id,
    append_unique_by_url,
    append_unique_evidence,
    append_unique_verdicts,
)


def _source(**overrides: object) -> Source:
    payload = {
        "run_id": uuid4(),
        "url": "https://example.com/article?utm_source=x#frag",
        "provenance": SourceProvenance(provider="searxng", query="q"),
    }
    payload.update(overrides)
    return Source.model_validate(payload)


def test_source_derives_canonical_url_and_domain() -> None:
    source = _source()
    assert source.canonical_url == source.url
    assert source.domain == "example.com"
    assert source.status.value == "pending"


def test_source_rejects_bad_urls() -> None:
    for url in ["ftp://example.com/x", "https://user:pass@example.com/x", "not-a-url"]:
        with pytest.raises(ValidationError):
            _source(url=url)
    with pytest.raises(ValidationError):
        _source(domain="")


def test_document_chunk_and_evidence_offsets() -> None:
    source = _source()
    document = Document(
        source_id=source.id,
        text="A long enough body of text for a chunk.",
        metadata=DocumentMetadata(title="Title"),
        content_hash="sha256:" + "a" * 64,
    )
    chunk = Chunk(
        source_id=source.id,
        document_id=document.id,
        ordinal=0,
        text="A long enough body",
        start_char=0,
        end_char=18,
        token_count=5,
        embedding=[0.1, 0.2],
    )
    span = EvidenceSpan(
        source_id=source.id,
        chunk_id=chunk.id,
        quote="A long enough body",
        start_char=0,
        end_char=18,
    )
    assert span.quote in chunk.text
    with pytest.raises(ValidationError):
        EvidenceSpan(
            source_id=source.id,
            chunk_id=chunk.id,
            quote="x",
            start_char=5,
            end_char=5,
        )


def test_claim_requires_citations_and_valid_markers() -> None:
    run_id = uuid4()
    claim = Claim(
        run_id=run_id,
        section="Intro",
        text="A claim.",
        citation_markers=["S1"],
    )
    assert claim.citation_markers == ["S1"]
    with pytest.raises(ValidationError):
        Claim(run_id=run_id, section="Intro", text="No citation", citation_markers=[])
    with pytest.raises(ValidationError):
        Claim(run_id=run_id, section="Intro", text="Bad marker", citation_markers=["X1"])


def test_claim_verdict_requires_evidence_for_support() -> None:
    claim_id = uuid4()
    with pytest.raises(ValidationError):
        ClaimVerdict(
            claim_id=claim_id,
            verdict=Verdict.SUPPORTED,
            confidence=0.9,
            verifier_model="test",
        )
    evidence = ClaimEvidence(
        claim_id=claim_id,
        chunk_id=uuid4(),
        source_id=uuid4(),
        verdict=Verdict.SUPPORTED,
        score=0.9,
        quoted_span="quote",
        verifier_model="test",
    )
    verdict = ClaimVerdict(
        claim_id=claim_id,
        verdict=Verdict.SUPPORTED,
        confidence=0.9,
        evidence=[evidence],
        verifier_model="test",
    )
    assert verdict.verdict is Verdict.SUPPORTED


def test_claim_bundle_resolves_all_markers() -> None:
    run_id = uuid4()
    claim = Claim(run_id=run_id, section="Intro", text="Claim", citation_markers=["S1"])
    verdict = ClaimVerdict(
        claim_id=claim.id,
        verdict=Verdict.INSUFFICIENT,
        confidence=0.4,
        verifier_model="test",
    )
    citation = Citation(
        claim_id=claim.id,
        source_id=uuid4(),
        chunk_id=uuid4(),
        marker="S1",
    )
    bundle = ClaimBundle(claim=claim, verdict=verdict, citations=[citation])
    assert bundle.claim.id == claim.id
    with pytest.raises(ValidationError):
        ClaimBundle(claim=claim, verdict=verdict, citations=[])


def test_research_plan_rejects_duplicate_ids_and_missing_dependencies() -> None:
    sub = SubQuestion(id="sq-one", question="What is X?")
    plan = ResearchPlan(question="Question?", sub_questions=[sub])
    assert plan.sub_questions[0].id == "sq-one"
    with pytest.raises(ValidationError):
        ResearchPlan(question="Question?", sub_questions=[sub, sub])
    with pytest.raises(ValidationError):
        ResearchPlan(
            question="Question?",
            sub_questions=[SubQuestion(id="sq-two", question="What is Y?", depends_on=["missing"])],
        )


def test_final_report_rejects_unresolved_markers() -> None:
    run_id = uuid4()
    source = _source(run_id=run_id)
    claim = Claim(run_id=run_id, section="Intro", text="Claim", citation_markers=["S1"])
    verdict = ClaimVerdict(
        claim_id=claim.id,
        verdict=Verdict.INSUFFICIENT,
        confidence=0.4,
        verifier_model="test",
    )
    citation = Citation(claim_id=claim.id, source_id=source.id, chunk_id=uuid4(), marker="S1")
    bundle = ClaimBundle(claim=claim, verdict=verdict, citations=[citation])
    section = ReportSection(title="Intro", markdown="Claim [S1]", claim_ids=[claim.id])
    with pytest.raises(ValidationError):
        FinalReport(
            run_id=run_id,
            question="Q?",
            markdown="Claim [S1]",
            sections=[section],
            claims=[bundle],
            citations=[],
            sources=[source],
        )


def test_run_context_and_approval() -> None:
    run = RunContext(
        run_id=uuid4(),
        trace_id="trace-1",
        question="What is X?",
        architecture=Architecture.SINGLE_AGENT,
    )
    assert run.user_id == "local"
    approval = ApprovalRequest(
        run_id=run.run_id,
        kind=ApprovalKind.EXPORT,
        payload={"report": "x"},
    )
    assert approval.status is ApprovalStatus.PENDING


def test_token_usage_and_budget() -> None:
    first = TokenUsage(input_tokens=10, output_tokens=5, requests=1)
    second = TokenUsage(input_tokens=2, output_tokens=3, requests=1)
    assert (first + second).total_tokens == 20
    ledger = UsageLedger(total=first, by_node={"planner": first})
    budget = BudgetState(limits=BudgetLimits(), usage=ledger)
    assert budget.total_tokens == 15
    assert budget.with_usage(ledger).usage is ledger


def test_coverage_and_critique_models() -> None:
    gap = CoverageGap(sub_question_id="sq-one", reason="missing")
    coverage = CoverageReport(
        sub_question_coverage={"sq-one": 0.0},
        gaps=[gap],
        total_sources=1,
        total_evidence_spans=2,
    )
    assert not coverage.is_sufficient
    decision = CritiqueDecision(route="research", gaps=[gap], confidence=0.5)
    assert decision.route == "research"
    assert ReportDraft(sections=[ReportSection(title="Intro", markdown="x")]).revision == 0


def test_state_reducers_dedupe() -> None:
    run_id = uuid4()
    source_a = _source(run_id=run_id)
    source_b = _source(run_id=run_id, url="https://other.example/x")
    assert len(append_unique_by_url([source_a], [source_a, source_b])) == 2

    claim = Claim(run_id=run_id, section="Intro", text="Claim", citation_markers=["S1"])
    assert len(append_unique_by_id([claim], [claim])) == 1

    verdict = ClaimVerdict(
        claim_id=claim.id,
        verdict=Verdict.INSUFFICIENT,
        confidence=0.2,
        verifier_model="test",
    )
    updated = verdict.model_copy(update={"confidence": 0.8})
    merged = append_unique_verdicts([verdict], [updated])
    assert len(merged) == 1
    assert merged[0].confidence == 0.8

    span = EvidenceSpan(
        source_id=source_a.id,
        chunk_id=uuid4(),
        quote="quote",
        start_char=0,
        end_char=5,
    )
    assert len(append_unique_evidence([span], [span])) == 1

    state: ResearchState = {"sources": [source_a], "errors": [], "warnings": []}
    assert state["sources"][0].id == source_a.id
