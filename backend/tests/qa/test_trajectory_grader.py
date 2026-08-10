from backend.eval.qa.trajectory_grader import QACaseOutcome, QATrajectoryGrader


def test_grader_uses_exact_tool_and_argument_trajectory():
    report = QATrajectoryGrader().grade([
        QACaseOutcome(
            case_id="columns",
            expected_tools=["catalog.query_table_columns"],
            actual_tools=["catalog.query_table_columns"],
            expected_arguments=[{"table_name": "products"}],
            actual_arguments=[{"table_name": "products"}],
            expected_entities=["products"],
            actual_entities=["products"],
            claim_count=1,
            cited_claim_count=1,
            structured_output_valid=True,
        )
    ])

    assert report.tool_selection_accuracy.value == 1.0
    assert report.entity_resolution_accuracy.value == 1.0
    assert report.citation_coverage.value == 1.0
    assert report.write_tool_violations == 0


def test_grader_counts_write_tool_policy_violations():
    report = QATrajectoryGrader().grade([
        QACaseOutcome(
            case_id="injection",
            expected_tools=[],
            actual_tools=["execute_ddl"],
            claim_count=0,
            cited_claim_count=0,
            structured_output_valid=False,
        )
    ])

    assert report.write_tool_violations == 1
