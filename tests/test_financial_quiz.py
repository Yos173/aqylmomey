from bot.services.financial_quiz import QUIZ_QUESTIONS, public_questions, score_quiz


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
