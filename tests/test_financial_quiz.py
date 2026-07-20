from bot.services.financial_quiz import QUIZ_QUESTIONS, public_questions, review_quiz, score_quiz


def test_public_questions_hide_correct_index():
    questions = public_questions()
    assert len(questions) == len(QUIZ_QUESTIONS)
    for q in questions:
        assert "correct_index" not in q
        assert "text" in q
        assert "options" in q


def test_score_quiz_all_correct():
    answers = [q["correct_index"] for q in QUIZ_QUESTIONS]
    correct, total = score_quiz(answers)
    assert correct == total == len(QUIZ_QUESTIONS)


def test_score_quiz_all_wrong():
    answers = [(q["correct_index"] + 1) % len(q["options"]) for q in QUIZ_QUESTIONS]
    correct, total = score_quiz(answers)
    assert correct == 0
    assert total == len(QUIZ_QUESTIONS)


def test_score_quiz_partial():
    answers = [q["correct_index"] for q in QUIZ_QUESTIONS]
    answers[0] = (answers[0] + 1) % len(QUIZ_QUESTIONS[0]["options"])
    correct, total = score_quiz(answers)
    assert correct == total - 1


def test_score_quiz_missing_answers_counted_as_wrong():
    correct, total = score_quiz([])
    assert correct == 0
    assert total == len(QUIZ_QUESTIONS)


def test_score_quiz_ignores_extra_answers():
    answers = [q["correct_index"] for q in QUIZ_QUESTIONS] + [0, 1, 2]
    correct, total = score_quiz(answers)
    assert correct == total == len(QUIZ_QUESTIONS)


def test_review_quiz_all_correct_has_no_mistakes():
    answers = [q["correct_index"] for q in QUIZ_QUESTIONS]
    assert review_quiz(answers) == []


def test_review_quiz_reports_wrong_answer_with_correct_option_and_explanation():
    answers = [q["correct_index"] for q in QUIZ_QUESTIONS]
    wrong_index = (answers[0] + 1) % len(QUIZ_QUESTIONS[0]["options"])
    answers[0] = wrong_index

    mistakes = review_quiz(answers)
    assert len(mistakes) == 1
    assert mistakes[0]["question"] == QUIZ_QUESTIONS[0]["text"]
    assert mistakes[0]["your_answer"] == QUIZ_QUESTIONS[0]["options"][wrong_index]
    assert mistakes[0]["correct_answer"] == QUIZ_QUESTIONS[0]["options"][QUIZ_QUESTIONS[0]["correct_index"]]
    assert mistakes[0]["explanation"]


def test_review_quiz_missing_answer_has_no_your_answer():
    mistakes = review_quiz([])
    assert len(mistakes) == len(QUIZ_QUESTIONS)
    assert all(m["your_answer"] is None for m in mistakes)
