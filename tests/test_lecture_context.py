import re

from app import lecture_context
from app.lecture_context import build_lecture_context
from app.flows import lecture_flow


def test_short_lecture_is_sent_in_full():
    lecture = "Программная инженерия возникла в 1968 году."

    context, mode = build_lecture_context(lecture, "В каком году возникла программная инженерия?", "a. 1968")

    assert context == lecture
    assert mode == "full"


def test_long_lecture_selects_relevant_fragment():
    noise = "Общие сведения о проектировании информационных систем.\n" * 1000
    answer = "Термин программная инженерия был закреплён на конференции НАТО в 1968 году."
    lecture = f"{noise}\n{answer}\n{noise}"

    context, mode = build_lecture_context(
        lecture,
        "В каком году зародилась программная инженерия?",
        "a. 1954\nb. 1968\nc. 1980",
    )

    assert mode == "selected"
    assert "1968 году" in context
    assert len(context) <= 18000


def test_large_single_topic_uses_selected_context_before_model_limit():
    lecture = ("CRM повышает результативность работы предприятия.\n" * 1000).strip()

    context, mode = build_lecture_context(
        lecture,
        "Введение CRM-системы повышает результативность?",
    )

    assert len(lecture) > lecture_context.FULL_CONTEXT_LIMIT
    assert mode == "selected"
    assert len(context) <= lecture_context.SELECTED_CONTEXT_LIMIT


def test_context_keeps_strong_matches_before_neighbour_chunks(monkeypatch):
    chunks = [(f"NOISE_{index} " + "обычный текст " * 180) for index in range(8)]
    chunks.extend(
        [
            "PRIMARY_ALPHA alpha alpha alpha " + "текст " * 400,
            "PRIMARY_BETA beta beta beta " + "текст " * 400,
            "PRIMARY_GAMMA gamma gamma gamma " + "текст " * 400,
            "PRIMARY_DELTA delta delta delta " + "текст " * 400,
        ]
    )
    monkeypatch.setattr(lecture_context, "split_text", lambda _text: chunks)

    context, mode = build_lecture_context(
        "x" * 50000,
        "alpha beta gamma delta",
    )

    assert mode == "selected"
    assert len(context) <= 18000
    assert all(
        marker in context
        for marker in ("PRIMARY_ALPHA", "PRIMARY_BETA", "PRIMARY_GAMMA", "PRIMARY_DELTA")
    )


def test_expanded_retry_uses_more_relevant_chunks(monkeypatch):
    chunks = [f"MATCH_{index} alpha " + "текст " * 400 for index in range(12)]
    monkeypatch.setattr(lecture_context, "split_text", lambda _text: chunks)

    focused, focused_mode = build_lecture_context("x" * 50000, "alpha")
    expanded, expanded_mode = build_lecture_context(
        "x" * 50000,
        "alpha",
        strategy="expanded",
    )

    assert focused_mode == "selected"
    assert expanded_mode == "expanded"
    assert len(expanded) > len(focused)
    assert len(expanded) <= lecture_context.EXPANDED_CONTEXT_LIMIT


def test_final_context_skips_unavailable_lecture_placeholder(tmp_path, monkeypatch):
    course_folder = tmp_path / "HTML Courses" / "Курс"
    course_folder.mkdir(parents=True)
    (course_folder / "Тема 1_2026-01-01_10-00-00.txt").write_text(
        "Блоки\nЭта лекция ещё не готова к использованию.\nБлоки",
        encoding="utf-8",
    )
    (course_folder / "Тема 2_2026-01-01_10-00-00.txt").write_text(
        "Полноценный материал лекции. " * 30,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    context = lecture_flow.load_saved_course_context("Курс")

    assert "ещё не готова" not in context
    assert "Полноценный материал" in context


def test_numbered_topic_collects_all_sublecture_parts_and_rejects_literature():
    names = [
        "Лекция 1.5. Краткая история Python. Часть 5",
        "Дополнительная литература по дисциплине Python ч.1",
        "Лекция 1.1. Краткая история Python. Часть 1",
        "Лекция 2.1. Синтаксис Python. Часть 1",
        "Лекция 1.3. Краткая история Python. Часть 3",
    ]
    candidates = []
    for index, name in enumerate(names):
        number_match = re.search(r"\b(\d+(?:[\.,]\d+)*)\b", name)
        number = number_match.group(1) if number_match else None
        if (
            lecture_flow._is_numbered_lecture_material(name)
            and lecture_flow._lecture_number_matches("1", number)
        ):
            candidates.append((number, name, f"url-{index}"))

    selected = lecture_flow._deduplicate_and_sort_candidates(candidates)

    assert [item[0] for item in selected] == ["1.1", "1.3", "1.5"]
    assert all("Дополнительная литература" not in item[1] for item in selected)


def test_decimal_test_number_only_matches_exact_lecture_part():
    assert lecture_flow._lecture_number_matches("1.2", "1.2") is True
    assert lecture_flow._lecture_number_matches("1.2", "1.1") is False
    assert lecture_flow._lecture_number_matches("1.2", "1.2.1") is False
