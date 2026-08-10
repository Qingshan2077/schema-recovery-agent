from backend.agent.qa.answer_verifier import AnswerVerifier
from backend.agent.qa.contracts import AnswerClaim, Citation, FactSet, SynthesisDraft, VerifiedFact


def fact() -> VerifiedFact:
    return VerifiedFact(
        fact_id="fact_one",
        fact_type="column",
        subject_id="products:id",
        predicate="has_column",
        value={"name": "id", "data_type": "bigint"},
        source_tool_call_id="tcall_one",
        source_tool="catalog.query_table_columns",
        output_hash="abc",
        locator={"table": "products", "column": "id"},
    )


def test_rejects_answer_text_outside_grounded_claims():
    draft = SynthesisDraft(
        answer="products has id\nand also a secret column",
        claims=[AnswerClaim(claim_id="claim_one", text="products has id", fact_ids=["fact_one"])],
        citations=[Citation(citation_id="cit_one", claim_id="claim_one", fact_ids=["fact_one"], label="catalog", locator={"tool_call_ids": ["tcall_one"], "fact_locators": [{"table": "products", "column": "id"}]})],
    )
    report = AnswerVerifier().verify(draft, FactSet(facts=[fact()], tool_call_ids=["tcall_one"], catalog_version="snp_one"))

    assert report.valid is False
    assert "answer contains text outside the verified claims" in report.errors


def test_accepts_fully_cited_exact_claim_text():
    draft = SynthesisDraft(
        answer="products has id",
        claims=[AnswerClaim(claim_id="claim_one", text="products has id", fact_ids=["fact_one"])],
        citations=[Citation(citation_id="cit_one", claim_id="claim_one", fact_ids=["fact_one"], label="catalog", locator={"tool_call_ids": ["tcall_one"], "fact_locators": [{"table": "products", "column": "id"}]})],
    )

    report = AnswerVerifier().verify(draft, FactSet(facts=[fact()], tool_call_ids=["tcall_one"], catalog_version="snp_one"))

    assert report.valid is True
    assert report.citation_coverage == 1.0
