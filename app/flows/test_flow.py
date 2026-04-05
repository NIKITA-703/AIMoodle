import re
import time
from datetime import datetime

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from app.ai_utils import ask_ai_question
from app.config import BOT_HISTORY_FILE, url_home_page


def start_test_attempt(driver):
    """Нажимает 'Пройти тест' и подтверждает."""
    print("🎯 Попытка начать тест... \n")
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(., 'Пройти тест') or contains(., 'Начать тестирование') or contains(., 'Продолжить')]",
                )
            )
        )
        btn.click()

        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='Начать попытку'] | //button[contains(., 'Начать попытку')]")
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
    found = re.findall(r'\b([a-z0-9]+)[\.\)]', ai_text.lower())

    if not found and len(ai_text) < 5:
        clean = ai_text.strip().lower().replace('.', '').replace(')', '')
        if clean:
            found = [clean]

    return found


def solve_active_test(driver, lecture_text):
    print("\n🤖 [AGENT] Режим решения активирован.")

    while True:
        try:
            time.sleep(2)

            if not driver.find_elements(By.CSS_SELECTOR, ".que") and driver.find_elements(By.CSS_SELECTOR, ".quizsummaryofattempt"):
                print("🏁 Вопросы кончились.")
                submit_test(driver)
                break

            try:
                q_block = driver.find_element(By.CSS_SELECTOR, ".que")
                q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
            except NoSuchElementException:
                print("⚠️ Не могу найти блок вопроса, пробую еще раз...")
                continue

            options_text = []
            options_map = {}
            question_type = "unknown"

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
                            question_type = inp.get_attribute("type")
                    except Exception:
                        continue

            print(f"\n❓ Вопрос ({question_type}): {q_text[:80]}...")

            variants_str = "\n".join(options_text)
            ai_ans = ask_ai_question(q_text, variants_str, lecture_text)

            target_keys = []
            text_answer_clean = ""

            if question_type == "text":
                text_answer_clean = ai_ans.strip().strip('"').strip("'").strip(".")
                text_answer_clean = re.sub(r"^\s*[a-zа-я0-9]+\s*[\.\)]\s+", "", text_answer_clean, flags=re.IGNORECASE)
                print(f"🤖 ИИ написал: '{text_answer_clean}'")

            elif question_type == "select":
                ai_lower = ai_ans.lower()
                for opt_key in options_map:
                    if opt_key in ai_lower or ai_lower in opt_key:
                        target_keys = [options_map[opt_key]]
                        print(f"🤖 ИИ выбрал селект: {target_keys[0]}")
                        break
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

                if target_keys:
                    print(f"🤖 ИИ выбрал: {target_keys}")
                else:
                    if options_map:
                        print("🆘 ИИ не дал букву. Выбираем первый вариант.")
                        target_keys = [list(options_map.keys())[0]]

            if question_type == "text":
                try:
                    inp = options_map["text_input"]
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                    inp.clear()
                    inp.send_keys(text_answer_clean)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"❌ Ошибка ввода текста: {e}")

            elif question_type == "select":
                try:
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

            try:
                driver.find_element(By.NAME, "next").click()
            except NoSuchElementException:
                pass

        except Exception as e:
            print(f"❌ Глобальная ошибка цикла: {e}")
            break


def parse_results(driver):
    """
    Парсит итоговую таблицу Moodle после завершения теста.
    """
    print("\n📊 --- ИТОГИ ТЕСТА ---")
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".quizreviewsummary")))

        try:
            time_taken = driver.find_element(By.XPATH, "//h5[contains(., 'Затраченное время')]/following-sibling::div").text
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


def submit_test(driver):
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
        time.sleep(2)

        driver.get(url_home_page)
        time.sleep(2)
    except Exception as e:
        print(f"⚠️ Ошибка финализации (возможно уже отправлен): {e}\n")
        driver.get(url_home_page)
