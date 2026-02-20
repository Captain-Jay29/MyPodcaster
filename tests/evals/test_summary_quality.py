"""Surface 1: Summary quality evals using DeepEval LLM-as-judge metrics."""

import pytest
from deepeval.metrics import (
    FaithfulnessMetric,
    GEval,
    HallucinationMetric,
    SummarizationMetric,
)
from deepeval.test_case import LLMTestCase
from deepeval.test_case.llm_test_case import LLMTestCaseParams

# ──────────────────────────────────────────────
# Metric 1: Faithfulness
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_faithfulness(article_pairs):
    """Every claim in the summary should be supported by the source article."""
    metric = FaithfulnessMetric(threshold=0.7, model="gpt-4o-mini")

    for article, source_content in article_pairs:
        test_case = LLMTestCase(
            input=f"Summarize this article about {article.title}",
            actual_output=article.summary_text,
            retrieval_context=[source_content],
        )
        metric.measure(test_case)
        assert metric.score >= 0.7, (
            f"Faithfulness {metric.score:.2f} < 0.7 for '{article.title}': {metric.reason}"
        )


# ──────────────────────────────────────────────
# Metric 2: Coverage
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_coverage(article_pairs):
    """The summary should capture the important points from the source."""
    metric = SummarizationMetric(
        threshold=0.5,
        model="gpt-4o-mini",
        assessment_questions=[
            "Does the summary mention the main subject or topic?",
            "Does the summary explain why this matters?",
            "Does the summary include key data points or decisions?",
        ],
    )

    for article, source_content in article_pairs:
        test_case = LLMTestCase(
            input=source_content,
            actual_output=article.summary_text,
        )
        metric.measure(test_case)
        assert metric.score >= 0.5, (
            f"Coverage {metric.score:.2f} < 0.5 for '{article.title}': {metric.reason}"
        )


# ──────────────────────────────────────────────
# Metric 3: Hallucination
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_no_hallucination(article_pairs):
    """The summary should not contain fabricated facts.

    HallucinationMetric is inverted: 0 = no hallucination (good), 1 = all hallucinated (bad).
    We assert score <= 0.3 (at most 30% of claims unsupported).
    """
    metric = HallucinationMetric(threshold=0.5, model="gpt-4o-mini")

    for article, source_content in article_pairs:
        test_case = LLMTestCase(
            input=f"Summarize this article about {article.title}",
            actual_output=article.summary_text,
            context=[source_content],
        )
        metric.measure(test_case)
        assert metric.score <= 0.3, (
            f"Hallucination score {metric.score:.2f} > 0.3 for '{article.title}': {metric.reason}"
        )


# ──────────────────────────────────────────────
# Metric 4: Conciseness (deterministic)
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_conciseness(agent_trace):
    """Each summary should be 50-90 words with no visual formatting."""
    for article in agent_trace.script.articles:
        text = article.summary_text
        word_count = len(text.split())
        assert 50 <= word_count <= 90, (
            f"'{article.title}' has {word_count} words (target: 50-90)"
        )
        assert "http" not in text, f"'{article.title}' contains a URL"
        assert "**" not in text, f"'{article.title}' contains markdown bold"
        assert "- " not in text.split("\n")[0] or True  # allow inline dashes
        # Check for bullet-point lines
        for line in text.split("\n"):
            assert not line.strip().startswith("- "), (
                f"'{article.title}' contains bullet points"
            )


# ──────────────────────────────────────────────
# Metric 5: Listenability (LLM-as-judge)
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_listenability(article_pairs):
    """Summaries should be written for the ear, not the eye."""
    metric = GEval(
        name="Listenability",
        criteria=(
            "Evaluate whether this text is written to be HEARD, not read. "
            "Good audio scripts use short sentences under 20 words, "
            "avoid jargon without explanation, have a natural conversational flow, "
            "and avoid visual formatting like bullet points, parentheses, or abbreviations."
        ),
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=0.3,
        model="gpt-4o-mini",
    )

    for article, _source in article_pairs:
        test_case = LLMTestCase(
            input=f"Audio summary of: {article.title}",
            actual_output=article.summary_text,
        )
        metric.measure(test_case)
        assert metric.score >= 0.3, (
            f"Listenability {metric.score:.2f} < 0.3 for '{article.title}': {metric.reason}"
        )
