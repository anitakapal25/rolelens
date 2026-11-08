from pathlib import Path

from app.eval.grading import Case, FitCheck, grade_case, grade_fit, load_eval_set

GOLDEN = Path(__file__).parents[1] / "app" / "eval" / "golden.yaml"


def test_committed_golden_set_is_valid_and_files_exist() -> None:
    eval_set = load_eval_set(GOLDEN)
    assert 12 <= len(eval_set.cases) <= 20
    assert sum(c.expect == "not_in_docs" for c in eval_set.cases) >= 3
    assert len({c.id for c in eval_set.cases}) == len(eval_set.cases)
    for spec in eval_set.documents.values():
        assert (GOLDEN.parent / spec.path).is_file()
    keys = set(eval_set.documents)
    for c in eval_set.cases:
        assert set(c.route or []) <= keys and set(c.must_cite) <= keys
    # Regression: an unquoted "Job #2" is cut at the " #" by YAML.
    assert any("Job #2" in c.question for c in eval_set.cases)


def test_grade_passes_when_everything_matches() -> None:
    case = Case(id="x", question="q", route=["resume", "job2"], must_include=[["PyTorch", "torch"]],
                must_not_include=["100%"], must_cite=["job2"])
    assert grade_case(case, "Job #2 needs PyTorch [3].", {"resume", "job2"}, {"job2"}) == []


def test_grade_reports_each_failure() -> None:
    case = Case(id="x", question="q", route=["resume", "job2"], must_include=[["PyTorch"]],
                must_not_include=["100%"], must_cite=["job2"])
    failures = grade_case(case, "You are a 100% fit.", {"resume", "job1"}, {"resume"})
    assert len(failures) == 4


def test_not_in_docs_and_off_topic_phrasing() -> None:
    not_in = Case(id="n", question="q", expect="not_in_docs")
    assert grade_case(not_in, "Your documents don’t show Rust.", set(), set()) == []
    assert grade_case(not_in, "Yes, you know Rust.", set(), set())
    off = Case(id="o", question="q", expect="off_topic")
    assert grade_case(off, "That's outside what RoleLens can help with.", set(), set()) == []
    assert grade_case(off, "Writing poems isn’t something RoleLens can help with.", set(), set()) == []
    assert grade_case(off, "Here is a poem about the sea...", set(), set())


def test_grade_fit_bounds() -> None:
    assert grade_fit(FitCheck(job="j", min_score=55), 60) == []
    assert grade_fit(FitCheck(job="j", max_score=54), 60) == ["score 60 > max 54"]
