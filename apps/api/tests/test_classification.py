"""
Milestone 6 -- Classifier unit tests.

Exercises LocalHeuristicClassifier directly (no mocks -- it's pure,
dependency-free logic) plus the registry resolution (get_classifier).
OpenAIClassifier is reviewed structurally, not tested against the real
network, matching this codebase's existing precedent for
OpenAIEmbeddingProvider/OpenAIChatProvider (services/embeddings.py,
services/llm.py).
"""

from app.models.resource import ResourceContentCategory
from app.services.classification import LocalHeuristicClassifier, get_classifier, reset_classifier_cache


def test_research_paper_signals_are_detected():
    text = "Abstract\nThis paper presents a novel approach. Keywords: ML.\nReferences\n[1] Smith et al. 2020."
    result = LocalHeuristicClassifier().classify(text, "paper.pdf")
    assert result.category == ResourceContentCategory.RESEARCH_PAPER
    assert 0.0 < result.category_confidence <= 0.95
    assert result.subject is None
    assert result.subject_confidence is None


def test_lab_manual_signals_are_detected():
    text = "Lab Manual\nExperiment No. 3\nAim: To determine resistance.\nProcedure: Connect the apparatus."
    result = LocalHeuristicClassifier().classify(text, "exp3.docx")
    assert result.category == ResourceContentCategory.LAB_MANUAL


def test_question_paper_signals_are_detected():
    text = "Question Paper\nTime: 3 Hours   Max Marks: 100\nAttempt any five questions from Section A."
    result = LocalHeuristicClassifier().classify(text, "midterm.pdf")
    assert result.category == ResourceContentCategory.QUESTION_PAPER


def test_assignment_signals_are_detected():
    text = "Assignment 2\nSubmit by Friday. This homework covers the due date policy."
    result = LocalHeuristicClassifier().classify(text, "hw2.docx")
    assert result.category == ResourceContentCategory.ASSIGNMENT


def test_lecture_signals_are_detected():
    text = "Lecture 5: Gradient Descent\nUnit 3, Chapter 2\nTopic: optimization"
    result = LocalHeuristicClassifier().classify(text, "lecture5.pptx")
    assert result.category == ResourceContentCategory.LECTURE


def test_pptx_extension_alone_biases_toward_lecture():
    # Weak/no keyword signal, but the slide-deck format itself is a real
    # (if soft) signal -- see classification.py's _LECTURE_EXTENSION_BONUS.
    text = "Just a few words on a slide."
    result = LocalHeuristicClassifier().classify(text, "deck.pptx")
    assert result.category == ResourceContentCategory.LECTURE


def test_personal_note_signals_are_detected():
    text = "Quick note to self: remember to review this before the exam. TODO: revise chapter 4."
    result = LocalHeuristicClassifier().classify(text, "note.txt")
    assert result.category == ResourceContentCategory.PERSONAL_NOTE


def test_no_signal_falls_back_to_other_with_low_confidence():
    result = LocalHeuristicClassifier().classify("random unrelated filler text", "file.txt")
    assert result.category == ResourceContentCategory.OTHER
    assert result.category_confidence == 0.2


def test_confidence_is_deterministic_for_identical_input():
    text = "Abstract and references and keywords and et al."
    a = LocalHeuristicClassifier().classify(text, "p.pdf")
    b = LocalHeuristicClassifier().classify(text, "p.pdf")
    assert a.category == b.category
    assert a.category_confidence == b.category_confidence


def test_more_matched_signals_yields_higher_confidence():
    weak = LocalHeuristicClassifier().classify("Keywords: x", "p.pdf")
    strong = LocalHeuristicClassifier().classify(
        "Abstract. Keywords: x. References. Smith et al. Methodology section.", "p.pdf"
    )
    assert strong.category_confidence > weak.category_confidence


def test_get_classifier_defaults_to_local_heuristic():
    # conftest.py's test environment sets no OPENAI_API_KEY, so this
    # confirms the same "zero-config golden path" default that
    # get_embedding_provider()/get_llm_provider() already rely on --
    # see app/services/classification.py's get_classifier().
    reset_classifier_cache()
    classifier = get_classifier()
    assert isinstance(classifier, LocalHeuristicClassifier)
    reset_classifier_cache()
