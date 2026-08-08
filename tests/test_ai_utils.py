from app import ai_utils
from app.ai_utils import (
    _answer_response_format,
    _evidence_in_context,
    ask_ai_question_data,
    clean_html_to_text,
    is_context_error_text,
    is_retryable_ai_error,
)


def test_clean_html_prefers_moodle_lesson_intro(tmp_path):
    html_path = tmp_path / "lecture.html"
    html_path.write_text(
        """
        <html><body><section id="region-main">
          <div class="activity-header">
            <div id="intro" class="activity-description">
              <div class="no-overflow">
                <h2>Методы утечки информации</h2>
                <p>Материально-технические каналы связаны с физическими носителями.</p>
                <p>К ним относятся бумажные документы, съёмные носители и диски.</p>
                <p>Для защиты применяются учёт, маркировка и разграничение доступа.</p>
                <p>Электромагнитные каналы возникают из-за побочных излучений.</p>
                <p>Организационные меры дополняются техническими средствами защиты.</p>
              </div>
            </div>
          </div>
          <div class="main-content">
            <div class="alert">Эта лекция ещё не готова к использованию.</div>
          </div>
        </section></body></html>
        """,
        encoding="utf-8",
    )

    text = clean_html_to_text(str(html_path))

    assert "Методы утечки информации" in text
    assert "физическими носителями" in text
    assert "ещё не готова" not in text


def test_context_placeholder_is_not_treated_as_lecture():
    text = "Блоки\nЭта лекция ещё не готова к использованию.\nБлоки"

    assert is_context_error_text(text)


def test_clean_html_extracts_moodle_page_generalbox(tmp_path):
    html_path = tmp_path / "page.html"
    html_path.write_text(
        """
        <html><body><section id="region-main">
          <div class="activity-header">Требуемые условия завершения</div>
          <div class="main-content" role="main">
            <div class="box generalbox">
              <div class="no-overflow">
                <h2>Архитектура операционной системы</h2>
                <p>Ядро UNIX имеет монолитную структуру.</p>
                <p>Подсистемы ядра выполняют управление процессами и памятью.</p>
                <p>Драйверы устройств обеспечивают взаимодействие с оборудованием.</p>
                <p>Системные вызовы образуют интерфейс пользовательских программ.</p>
                <p>Компоненты взаимодействуют внутри единого адресного пространства.</p>
              </div>
            </div>
          </div>
          <div>Последнее изменение: вчера</div>
        </section></body></html>
        """,
        encoding="utf-8",
    )

    text = clean_html_to_text(str(html_path))

    assert "Архитектура операционной системы" in text
    assert "монолитную структуру" in text
    assert "Требуемые условия" not in text
    assert "Последнее изменение" not in text


def test_ai_request_uses_bounded_structured_output(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                '{"answers":["b"],"text":"",'
                                '"source":"lecture","evidence":"Точная цитата лекции"}'
                            )
                        },
                    }
                ]
            }

    def fake_post(_url, json, timeout):
        captured["payload"] = json
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(ai_utils.requests, "post", fake_post)

    result = ask_ai_question_data(
        "Какой ответ?",
        "a. Первый\nb. Второй",
        "Точная цитата лекции подтверждает второй ответ.",
        question_type="radio",
        allowed_keys=["a", "b"],
    )

    assert result.answer_keys == ["b"]
    assert result.source == "lecture"
    assert captured["payload"]["max_tokens"] == 300
    assert captured["payload"]["response_format"]["type"] == "json_schema"
    assert captured["payload"]["response_format"]["json_schema"]["strict"] is True
    answers_schema = captured["payload"]["response_format"]["json_schema"]["schema"][
        "properties"
    ]["answers"]
    assert answers_schema["minItems"] == 1
    assert answers_schema["maxItems"] == 1
    assert answers_schema["items"]["enum"] == ["a", "b"]
    assert captured["timeout"] == 90


def test_length_limited_garbage_is_not_accepted_as_answer(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "任何人都" * 100},
                    }
                ]
            }

    monkeypatch.setattr(ai_utils.requests, "post", lambda *args, **kwargs: Response())

    result = ask_ai_question_data(
        "Какой ответ?",
        "a. Первый\nb. Второй",
        "Лекция",
        question_type="radio",
    )

    assert result.answer_keys == []
    assert result.text_answer == ""
    assert "任何人都" in result.raw_text


def test_lecture_evidence_accepts_line_breaks_and_minor_inflections():
    context = """
    Сервис обслуживания:
    включает в себя способности, связанные с масштабом и производительностью.
    """
    evidence = (
        "Сервисы обслуживания включают в себя способности, "
        "связанные с масштабом и производительностью"
    )

    assert _evidence_in_context(evidence, context) is True
    assert _evidence_in_context("точная короткая цитата", context) is False


def test_read_timeout_is_retryable_but_invalid_answer_is_not():
    assert is_retryable_ai_error("Ошибка соединения: Read timed out. (read timeout=90)")
    assert not is_retryable_ai_error("Пустой ответ LM Studio")


def test_checkbox_schema_requires_a_real_allowed_answer():
    response_format = _answer_response_format("checkbox", ["a", "b", "c", "d"])
    properties = response_format["json_schema"]["schema"]["properties"]

    assert properties["answers"]["minItems"] == 1
    assert properties["answers"]["maxItems"] == 4
    assert properties["answers"]["items"]["enum"] == ["a", "b", "c", "d"]
    assert properties["text"]["enum"] == [""]


def test_text_schema_requires_nonempty_text_and_forbids_choice_keys():
    response_format = _answer_response_format("text")
    properties = response_format["json_schema"]["schema"]["properties"]

    assert properties["answers"]["maxItems"] == 0
    assert properties["text"]["minLength"] == 1
