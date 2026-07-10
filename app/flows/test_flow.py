import re
import time
import traceback
from datetime import datetime

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from app.ai_utils import ask_ai_question, normalize_text_answer
from app.config import BOT_HISTORY_FILE, url_home_page
from app.quiz_memory import get_confirmed_answer, record_review_results


def start_test_attempt(driver):
    """Нажимает 'Пройти тест' и подтверждает."""
    print("🎯 Попытка начать тест... \n")
    try:
        if driver.find_elements(By.CSS_SELECTOR, ".que"):
            print("↩️ Попытка уже открыта, продолжаем текущий тест.\n")
            return True

        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(., 'Продолжить текущую попытку') "
                    "or contains(., 'Продолжить последнюю попытку') "
                    "or contains(., 'Пройти тест') "
                    "or contains(., 'Начать тестирование') "
                    "or contains(., 'Продолжить')]",
                )
            )
        )
        btn.click()

        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//input[@value='Начать попытку'] "
                        "| //button[contains(., 'Начать попытку')] "
                        "| //input[@value='Начать новую попытку'] "
                        "| //button[contains(., 'Начать новую попытку')]",
                    )
                )
            )
            confirm.click()
        except Exception:
            pass

        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".que")))
        print("🚀 Тест запущен!\n")
        return True
    except Exception as e:
        print(f"❌ Не удалось войти в тест: {e}\n")
        return False


def extract_answers(ai_text):
    """
    Умный парсинг ответа ИИ.
    Ищет буквы (a-z) или цифры (0-9) перед точкой или скобкой.
    """
    if ai_text is None:
        return []

    if not isinstance(ai_text, str):
        ai_text = str(ai_text)

    found = re.findall(r"\b([a-z0-9]+)[\.\)]", ai_text.lower())

    if not found and len(ai_text) < 5:
        clean = ai_text.strip().lower().replace(".", "").replace(")", "")
        if clean:
            found = [clean]

    return found


def _get_question_type_and_options(q_block):
    options_text = []
    options_map = {}
    question_type = "unknown"
    select_obj = None

    select_elements = q_block.find_elements(By.TAG_NAME, "select")
    text_inputs = q_block.find_elements(By.CSS_SELECTOR, "input[type='text'][name^='q']")

    if select_elements:
        question_type = "select"
        select_obj = Select(select_elements[0])
        for opt in select_obj.options:
            txt = opt.text.strip()
            if "выбрать" not in txt.lower() and txt:
                options_text.append(txt)
                options_map[txt.lower()] = txt
    elif text_inputs:
        question_type = "text"
        options_map["text_input"] = text_inputs[0]
    else:
        options_elements = q_block.find_elements(By.CSS_SELECTOR, ".answer div[class^='r']")

        for index, opt in enumerate(options_elements):
            try:
                txt = opt.text.strip()
                options_text.append(txt)

                try:
                    key = opt.find_element(By.CSS_SELECTOR, ".answernumber").text.lower().strip(" .)")
                except Exception:
                    key = "opt_" + str(index)

                try:
                    inp = opt.find_element(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                except Exception:
                    inp = opt.find_element(By.TAG_NAME, "input")

                options_map[key] = inp

                if question_type == "unknown":
                    input_type = inp.get_attribute("type")
                    if input_type:
                        question_type = input_type
            except Exception:
                continue

    return question_type, options_text, options_map, select_obj


def _get_text_answer_hint(q_text):
    gap_matches = re.findall(r"(?:\.{3,}|…)", q_text)
    gaps_count = len(gap_matches)

    if gaps_count >= 2:
        return f"В вопросе {gaps_count} пропуска. Ответ должен быть кратким и, скорее всего, состоять примерно из {gaps_count} слов."
    if gaps_count == 1:
        return "В вопросе один пропуск. Ответ должен быть кратким и, скорее всего, состоять из одного слова."
    if "вставьте недостающее слово" in q_text.lower():
        return "Нужно вставить недостающее слово. Ответ должен быть кратким и в точной форме."
    return ""


def _build_text_retry_hint(answer_hint):
    base = answer_hint or "Ответ должен быть кратким."
    return base + " Обязательно верни непустой ответ без пояснений."


def _ensure_min_checkbox_answers(target_keys, options_map, min_answers=2):
    if len(target_keys) >= min_answers:
        return target_keys

    ordered_keys = [key for key in options_map.keys() if key not in target_keys]
    while len(target_keys) < min_answers and ordered_keys:
        target_keys.append(ordered_keys.pop(0))
    return target_keys


def _normalize_option_text(text):
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"^\s*[a-zа-я0-9]+\s*[\.\)]\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _build_option_text_by_key(options_text, options_map):
    option_text_by_key = {}

    if not options_map:
        return option_text_by_key

    if options_text:
        for key, txt in zip(options_map.keys(), options_text):
            option_text_by_key[key] = txt

    for key in options_map.keys():
        option_text_by_key.setdefault(key, key)

    return option_text_by_key


def _find_keys_by_texts(target_texts, option_text_by_key):
    found_keys = []
    normalized_targets = [_normalize_option_text(text) for text in target_texts if text]

    for target in normalized_targets:
        if not target:
            continue
        for key, option_text in option_text_by_key.items():
            option_normalized = _normalize_option_text(option_text)
            if not option_normalized:
                continue
            if target == option_normalized or target in option_normalized or option_normalized in target:
                if key not in found_keys:
                    found_keys.append(key)
                break

    return found_keys


def _is_question_already_answered(q_block, question_type, options_map, select_obj):
    try:
        state_text = q_block.find_element(By.CSS_SELECTOR, ".state").text.strip().lower()
        if "ответ сохранен" in state_text or "выполнен" in state_text:
            return True
    except Exception:
        pass

    if question_type == "text":
        inp = options_map.get("text_input")
        return bool(inp and inp.get_attribute("value").strip())

    if question_type == "select" and select_obj:
        try:
            selected_text = select_obj.first_selected_option.text.strip()
            return bool(selected_text and "выбрать" not in selected_text.lower())
        except Exception:
            return False

    if question_type in {"radio", "checkbox"}:
        for value in options_map.values():
            try:
                if value.is_selected():
                    return True
            except Exception:
                continue

    return False


def _answer_question_block(driver, q_block, lecture_text, course_name="", test_name=""):
    q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
    question_label = "?"

    try:
        question_label = q_block.find_element(By.CSS_SELECTOR, ".qno").text.strip()
    except Exception:
        pass

    question_type, options_text, options_map, select_obj = _get_question_type_and_options(q_block)
    option_text_by_key = _build_option_text_by_key(options_text, options_map)

    if _is_question_already_answered(q_block, question_type, options_map, select_obj):
        print(f"⏭️ Вопрос {question_label} уже заполнен, пропускаем.")
        return

    print(f"\n❓ Вопрос {question_label} ({question_type}): {q_text[:80]}...")

    target_keys = []
    text_answer_clean = ""
    saved_answer = get_confirmed_answer(course_name, test_name, q_text)

    if saved_answer:
        print(f"🧠 Используем сохраненный ответ ({saved_answer.get('source', 'memory')}).")

        if question_type == "text":
            text_answer_clean = (saved_answer.get("text") or "").strip()
        elif question_type == "select":
            saved_texts = saved_answer.get("texts") or []
            if saved_texts:
                target_keys = [saved_texts[0]]
        else:
            target_keys = list(saved_answer.get("keys") or [])
            if not target_keys:
                target_keys = _find_keys_by_texts(saved_answer.get("texts") or [], option_text_by_key)
    else:
        answer_hint = _get_text_answer_hint(q_text) if question_type == "text" else ""
        variants_str = "\n".join(options_text)
        ai_ans = ask_ai_question(q_text, variants_str, lecture_text, answer_hint=answer_hint)

        if ai_ans is None:
            ai_ans = ""
        elif not isinstance(ai_ans, str):
            ai_ans = str(ai_ans)

        if question_type == "text":
            text_answer_clean = ai_ans.strip().strip('"').strip("'").strip(".")
            text_answer_clean = normalize_text_answer(q_text, text_answer_clean, answer_hint=answer_hint)

            if not text_answer_clean:
                retry_hint = _build_text_retry_hint(answer_hint)
                retry_ans = ask_ai_question(q_text, variants_str, lecture_text, answer_hint=retry_hint)
                if retry_ans is None:
                    retry_ans = ""
                elif not isinstance(retry_ans, str):
                    retry_ans = str(retry_ans)
                text_answer_clean = retry_ans.strip().strip('"').strip("'").strip(".")
                text_answer_clean = normalize_text_answer(q_text, text_answer_clean, answer_hint=retry_hint)

            text_answer_clean = re.sub(r"^\s*[a-zа-я0-9]+\s*[\.\)]\s+", "", text_answer_clean, flags=re.IGNORECASE)
            text_answer_clean = re.sub(r"\s*\([^)]*\)", "", text_answer_clean)
            text_answer_clean = " ".join(text_answer_clean.split())
            print(f"🤖 ИИ написал: '{text_answer_clean}'")

        elif question_type == "select":
            ai_lower = ai_ans.lower()
            for opt_key in options_map:
                if opt_key in ai_lower or ai_lower in opt_key:
                    target_keys = [options_map[opt_key]]
                    print(f"🤖 ИИ выбрал селект: {target_keys[0]}")
                    break
            if not target_keys:
                matched_by_text = _find_keys_by_texts([ai_ans], option_text_by_key)
                if matched_by_text:
                    target_keys = [options_map[matched_by_text[0]]]
            if not target_keys and options_text:
                target_keys = [options_text[0]]

        else:
            extracted_all = extract_answers(ai_ans)

            if question_type == "radio":
                if extracted_all:
                    last_key = extracted_all[-1]
                    if last_key in options_map:
                        target_keys = [last_key]
                    else:
                        valid_keys = [k for k in reversed(extracted_all) if k in options_map]
                        if valid_keys:
                            target_keys = [valid_keys[0]]
                else:
                    target_keys = []
            else:
                target_keys = list(set([k for k in extracted_all if k in options_map]))

            if not target_keys:
                target_keys = _find_keys_by_texts([ai_ans], option_text_by_key)

            if question_type == "checkbox":
                before_expand = list(target_keys)
                target_keys = _ensure_min_checkbox_answers(target_keys, options_map, min_answers=2)
                if len(before_expand) < 2 <= len(target_keys):
                    print(f"➕ Для checkbox добавили варианты до минимума: {target_keys}")

            if target_keys:
                print(f"🤖 ИИ выбрал: {target_keys}")
            elif options_map:
                if question_type == "checkbox":
                    print("🆘 ИИ не дал буквы. Для checkbox выбираем минимум два варианта.")
                    target_keys = _ensure_min_checkbox_answers([], options_map, min_answers=2)
                else:
                    print("🆘 ИИ не дал букву. Выбираем первый вариант.")
                    first_key = next(iter(options_map.keys()), None)
                    if first_key is not None:
                        target_keys = [first_key]

    if question_type == "text":
        try:
            inp = options_map.get("text_input")
            if inp is None:
                print("⚠️ Не найдено поле ввода текста.")
                return
            if not text_answer_clean:
                print("⚠️ Пустой ответ для текстового вопроса. Оставляем поле без изменения.")
                return
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
            inp.clear()
            inp.send_keys(text_answer_clean)
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка ввода текста: {e}")

    elif question_type == "select":
        try:
            if target_keys:
                select_obj.select_by_visible_text(target_keys[0])
                time.sleep(0.5)
        except Exception as e:
            print(f"❌ Ошибка выбора в селекте: {e}")

    else:
        for key in target_keys:
            if key in options_map:
                el = options_map[key]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                if not el.is_selected():
                    driver.execute_script("arguments[0].click();", el)
                    time.sleep(0.3)


def solve_active_test(driver, lecture_text, course_name="", test_name=""):
    print("\n🤖 [AGENT] Режим решения активирован.")

    while True:
        try:
            time.sleep(2)

            if not driver.find_elements(By.CSS_SELECTOR, ".que") and driver.find_elements(
                By.CSS_SELECTOR, ".quizsummaryofattempt"
            ):
                print("🏁 Вопросы кончились.")
                submit_test(driver, course_name=course_name, test_name=test_name)
                break

            question_blocks = driver.find_elements(By.CSS_SELECTOR, ".que")
            if not question_blocks:
                print("⚠️ Не могу найти блоки вопросов, пробую еще раз...")
                continue

            for q_block in question_blocks:
                try:
                    _answer_question_block(driver, q_block, lecture_text, course_name=course_name, test_name=test_name)
                except NoSuchElementException:
                    print("⚠️ Не могу найти структуру одного из вопросов, пропускаю его.")
                except Exception as e:
                    print(f"❌ Ошибка обработки вопроса: {e}")
                    print(traceback.format_exc())

            next_buttons = driver.find_elements(By.NAME, "next")
            if next_buttons:
                next_buttons[0].click()
                continue

            end_attempt_buttons = driver.find_elements(
                By.XPATH,
                "//input[contains(@value, 'Закончить попытку')] | //button[contains(., 'Закончить попытку')] | "
                "//input[contains(@value, 'Завершить попытку')] | //button[contains(., 'Завершить попытку')]",
            )
            if end_attempt_buttons:
                end_attempt_buttons[0].click()
                time.sleep(2)
                continue

            finish_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Отправить всё')] | //input[@value='Отправить всё и завершить тест']",
            )
            if finish_buttons:
                submit_test(driver, course_name=course_name, test_name=test_name)
                break

            print("⚠️ Не нашел кнопку перехода дальше или завершения теста.")
            break
        except Exception as e:
            print(f"❌ Глобальная ошибка цикла: {e}")
            print(traceback.format_exc())
            break


def parse_results(driver):
    """
    Парсит итоговую таблицу Moodle после завершения теста.
    """
    print("\n📊 --- ИТОГИ ТЕСТА ---")
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".quizreviewsummary")))

        try:
            time_taken = driver.find_element(
                By.XPATH, "//h5[contains(., 'Затраченное время')]/following-sibling::div"
            ).text
            print(f"⏱️ Время: {time_taken}")
        except Exception:
            time_taken = "Не найдено"

        try:
            points = driver.find_element(By.XPATH, "//h5[contains(., 'Баллы')]/following-sibling::div").text
            print(f"🎯 Баллы: {points}")
        except Exception:
            points = "-"

        try:
            grade = driver.find_element(By.XPATH, "//h5[contains(., 'Оценка')]/following-sibling::div").text
            print(f"🏆 Оценка: {grade}")
        except Exception:
            grade = "-"

        with open(BOT_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] Время: {time_taken} | Баллы: {points} | Оценка: {grade}\n")
    except Exception as e:
        print(f"⚠️ Не удалось прочитать статистику: {e}")


def submit_test(driver, course_name="", test_name=""):
    """Отправляет тест на проверку"""
    try:
        finish_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'Отправить всё')] | //input[@value='Отправить всё и завершить тест']")
            )
        )
        finish_btn.click()

        modal_confirm = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-action='save']"))
        )
        modal_confirm.click()

        print("✅ ТЕСТ ЗАВЕРШЕН!")
        time.sleep(3)

        parse_results(driver)
        record_review_results(driver, course_name, test_name)
        time.sleep(2)

        driver.get(url_home_page)
        time.sleep(2)
    except Exception as e:
        print(f"⚠️ Ошибка финализации (возможно уже отправлен): {e}\n")
        driver.get(url_home_page)
