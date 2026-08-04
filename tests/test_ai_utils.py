from app.ai_utils import clean_html_to_text, is_context_error_text


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
