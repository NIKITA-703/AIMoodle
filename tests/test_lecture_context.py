from app.lecture_context import build_lecture_context


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
    assert len(context) <= 30000

