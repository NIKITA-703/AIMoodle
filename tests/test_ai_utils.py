from app.ai_utils import _parse_ai_result


def test_structured_answer_is_marked_as_lecture_when_quote_exists():
    context = "В лекции сказано: программная инженерия появилась в 1968 году."
    content = (
        '{"answers":["b"],"text":"","source":"lecture",'
        '"evidence":"программная инженерия появилась в 1968 году"}'
    )

    result = _parse_ai_result(content, "radio", context, "full")

    assert result.answer_keys == ["b"]
    assert result.source == "lecture"


def test_unconfirmed_quote_is_not_counted_as_lecture():
    content = '{"answers":["a"],"source":"lecture","evidence":"этой цитаты в лекции нет"}'

    result = _parse_ai_result(content, "radio", "Другой текст лекции", "full")

    assert result.source == "general_knowledge"
