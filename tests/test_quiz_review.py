from app.quiz_review import parse_question_reviews, parse_quiz_requirements, parse_review_summary


REQUIREMENTS_HTML = """
<div class="quizinfo">
  <p>Разрешено попыток: 3</p>
  <p>Проходная оценка: 60,00 из 100,00</p>
</div>
<div class="rui-attempts-list"><h4>Попытка 1</h4></div>
<button>Пройти тест заново</button>
"""


REVIEW_HTML = """
<div class="quizreviewsummary">
  <h5>Затраченное время</h5><div>4 мин. 18 сек.</div>
  <h5>Баллы</h5><div>1,50/3,00</div>
  <h5>Оценка</h5><div><b>50,00</b> из 100,00</div>
</div>
<div class="que multichoice">
  <div class="grade">Баллов: 1,00 из 1,00</div>
  <input class="questionflagpostdata" value="qaid=1&amp;qid=70474&amp;slot=1">
  <div class="qtext">Верно ли утверждение?</div>
  <div class="answer">
    <div class="r0"><input type="radio"><span class="answernumber">a.</span> Верно</div>
    <div class="r1"><input type="radio" checked><span class="answernumber">b.</span> Неверно</div>
  </div>
</div>
<div class="que multichoice">
  <div class="grade">Баллов: 0,50 из 1,00</div>
  <input class="questionflagpostdata" value="qaid=2&amp;qid=70475&amp;slot=2">
  <div class="qtext">Выберите виды диаграмм</div>
  <div class="answer">
    <div class="r0"><input type="checkbox" checked><span class="answernumber">a.</span> Классов</div>
    <div class="r1"><input type="checkbox" checked><span class="answernumber">b.</span> Объектов</div>
    <div class="r0"><input type="checkbox"><span class="answernumber">c.</span> Прецедентов</div>
  </div>
</div>
<div class="que multichoice">
  <div class="grade">Баллов: 0,00 из 1,00</div>
  <input class="questionflagpostdata" value="qaid=3&amp;qid=70476&amp;slot=3">
  <div class="qtext">Это правильно?</div>
  <div class="answer">
    <div class="r0"><input type="radio" checked><span class="answernumber">a.</span> Нет</div>
    <div class="r1"><input type="radio"><span class="answernumber">b.</span> Да</div>
  </div>
</div>
"""


TEXT_AND_SELECT_REVIEW_HTML = """
<div class="que shortanswer">
  <div class="grade">Баллов: 1,00 из 1,00</div>
  <input class="questionflagpostdata" value="qid=80001&amp;slot=1">
  <div class="qtext">Вставьте слово ...</div>
  <input type="text" value="тенденция">
</div>
<div class="que matching">
  <div class="grade">Баллов: 1,00 из 1,00</div>
  <input class="questionflagpostdata" value="qid=80002&amp;slot=2">
  <div class="qtext">Выберите значение</div>
  <select><option>Нет</option><option selected>Да</option></select>
</div>
"""


def test_parse_requirements_for_new_attempt():
    requirements = parse_quiz_requirements(REQUIREMENTS_HTML, course_id="74", quiz_id="6143")

    assert requirements.pass_grade == 60.0
    assert requirements.allowed_attempts == 3
    assert requirements.attempt_number == 2
    assert requirements.remaining_attempts_after_current == 1
    assert requirements.quiz_id == "6143"


def test_parse_requirements_for_continued_attempt():
    html = REQUIREMENTS_HTML.replace("Пройти тест заново", "Продолжить текущую попытку")

    requirements = parse_quiz_requirements(html)

    assert requirements.attempt_number == 1
    assert requirements.remaining_attempts_after_current == 2


def test_parse_review_summary():
    summary = parse_review_summary(REVIEW_HTML)

    assert summary.score == 1.5
    assert summary.max_score == 3.0
    assert summary.grade_percent == 50.0
    assert summary.time_taken == "4 мин. 18 сек."


def test_parse_review_questions_and_qid():
    questions = parse_question_reviews(REVIEW_HTML)

    assert len(questions) == 3
    assert questions[0].question_id == "70474"
    assert questions[0].selected_options[0].key == "b"
    assert questions[1].score == 0.5
    assert [option.key for option in questions[1].selected_options] == ["a", "b"]


def test_parse_text_and_select_questions():
    questions = parse_question_reviews(TEXT_AND_SELECT_REVIEW_HTML)

    assert [question.question_type for question in questions] == ["text", "select"]
    assert questions[0].text_answer == "тенденция"
    assert questions[1].selected_options[0].text == "Да"
