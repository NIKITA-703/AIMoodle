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
    """РќР°Р¶РёРјР°РµС‚ 'РџСЂРѕР№С‚Рё С‚РµСЃС‚' Рё РїРѕРґС‚РІРµСЂР¶РґР°РµС‚."""
    print("рџЋЇ РџРѕРїС‹С‚РєР° РЅР°С‡Р°С‚СЊ С‚РµСЃС‚... \n")
    try:
        # 1. РљРЅРѕРїРєР° "РџСЂРѕР№С‚Рё С‚РµСЃС‚"
        # 1. РС‰РµРј РєРЅРѕРїРєСѓ Р·Р°РїСѓСЃРєР°. Р”РѕР±Р°РІРёР»Рё 'РџСЂРѕРґРѕР»Р¶РёС‚СЊ'
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH,
                                        "//button[contains(., 'РџСЂРѕР№С‚Рё С‚РµСЃС‚') or contains(., 'РќР°С‡Р°С‚СЊ С‚РµСЃС‚РёСЂРѕРІР°РЅРёРµ') or contains(., 'РџСЂРѕРґРѕР»Р¶РёС‚СЊ')]"))
        )
        btn.click()

        # 2. РњРѕРґР°Р»РєР° "РќР°С‡Р°С‚СЊ РїРѕРїС‹С‚РєСѓ"
        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='РќР°С‡Р°С‚СЊ РїРѕРїС‹С‚РєСѓ'] | //button[contains(., 'РќР°С‡Р°С‚СЊ РїРѕРїС‹С‚РєСѓ')]"))
            )
            confirm.click()
        except:
            pass  # РњРѕР¶РµС‚ Рё РЅРµ Р±С‹С‚СЊ

        # 3. Р–РґРµРј РїРѕСЏРІР»РµРЅРёСЏ РІРѕРїСЂРѕСЃР°
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".que")))
        print("рџљЂ РўРµСЃС‚ Р·Р°РїСѓС‰РµРЅ!\n")
        return True
    except Exception as e:
        print(f"вќЊ РќРµ СѓРґР°Р»РѕСЃСЊ РІРѕР№С‚Рё РІ С‚РµСЃС‚: {e}\n")
        return False

def extract_answers(ai_text):
    """
    РЈРјРЅС‹Р№ РїР°СЂСЃРёРЅРі РѕС‚РІРµС‚Р° РР.
    РС‰РµС‚ Р±СѓРєРІС‹ (a-z) РёР»Рё С†РёС„СЂС‹ (0-9) РїРµСЂРµРґ С‚РѕС‡РєРѕР№ РёР»Рё СЃРєРѕР±РєРѕР№.
    """
    # 1. РС‰РµРј СЏРІРЅС‹Рµ СЃРїРёСЃРєРё: "a.", "b)", "1.", "1)"
    # [a-z0-9] - Р»СЋР±Р°СЏ Р±СѓРєРІР° РёР»Рё С†РёС„СЂР°
    found = re.findall(r'\b([a-z0-9]+)[\.\)]', ai_text.lower())

    # 2. Р•СЃР»Рё РЅРµ РЅР°С€Р»Рё, Рё РѕС‚РІРµС‚ РѕС‡РµРЅСЊ РєРѕСЂРѕС‚РєРёР№ (РЅР°РїСЂРёРјРµСЂ РїСЂРѕСЃС‚Рѕ "a" РёР»Рё "РґР°"), Р±РµСЂРµРј РІРµСЃСЊ С‚РµРєСЃС‚
    if not found and len(ai_text) < 5:
        clean = ai_text.strip().lower().replace('.', '').replace(')', '')
        if clean:
            found = [clean]

    return found

def solve_active_test(driver, lecture_text):
    print("\nрџ¤– [AGENT] Р РµР¶РёРј СЂРµС€РµРЅРёСЏ Р°РєС‚РёРІРёСЂРѕРІР°РЅ.")

    while True:
        try:
            time.sleep(2)  # Р”Р°РµРј РІСЂРµРјСЏ РЅР° РїСЂРѕРіСЂСѓР·РєСѓ Р°РЅРёРјР°С†РёР№

            # --- 1. РџР РћР’Р•Р РљРђ РќРђ РљРћРќР•Р¦ РўР•РЎРўРђ ---
            # Р•СЃР»Рё РЅРµС‚ РІРѕРїСЂРѕСЃРѕРІ, РЅРѕ РµСЃС‚СЊ С‚Р°Р±Р»РёС†Р° СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ -> СЃРґР°РµРј
            if not driver.find_elements(By.CSS_SELECTOR, ".que") and driver.find_elements(By.CSS_SELECTOR,
                                                                                          ".quizsummaryofattempt"):
                print("рџЏЃ Р’РѕРїСЂРѕСЃС‹ РєРѕРЅС‡РёР»РёСЃСЊ.")
                submit_test(driver)
                break

            # --- 2. РџРђР РЎРРќР“ Р’РћРџР РћРЎРђ ---
            try:
                q_block = driver.find_element(By.CSS_SELECTOR, ".que")
                q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
            except NoSuchElementException:
                print("вљ пёЏ РќРµ РјРѕРіСѓ РЅР°Р№С‚Рё Р±Р»РѕРє РІРѕРїСЂРѕСЃР°, РїСЂРѕР±СѓСЋ РµС‰Рµ СЂР°Р·...")
                continue

            options_text = []
            options_map = {}
            question_type = "unknown"

            # --- 3. РћРџР Р•Р”Р•Р›Р•РќРР• РўРРџРђ Р’РћРџР РћРЎРђ ---

            # Рђ) РџСЂРѕРІРµСЂСЏРµРј Р’С‹РїР°РґР°СЋС‰РёР№ СЃРїРёСЃРѕРє (Select)
            select_elements = q_block.find_elements(By.TAG_NAME, "select")

            # Р‘) РџСЂРѕРІРµСЂСЏРµРј Р’РІРѕРґ С‚РµРєСЃС‚Р° (Text Input)
            # РС‰РµРј input type='text', Сѓ РєРѕС‚РѕСЂРѕРіРѕ РёРјСЏ РЅР°С‡РёРЅР°РµС‚СЃСЏ РЅР° 'q' (СЃС‚Р°РЅРґР°СЂС‚ Moodle РґР»СЏ РѕС‚РІРµС‚РѕРІ)
            text_inputs = q_block.find_elements(By.CSS_SELECTOR, "input[type='text'][name^='q']")

            if select_elements:
                question_type = "select"
                select_obj = Select(select_elements[0])
                # РЎРѕР±РёСЂР°РµРј С‚РµРєСЃС‚ РѕРїС†РёР№ РґР»СЏ РР
                for opt in select_obj.options:
                    txt = opt.text.strip()
                    if "РІС‹Р±СЂР°С‚СЊ" not in txt.lower() and txt:  # РРіРЅРѕСЂРёСЂСѓРµРј "Р’С‹Р±РµСЂРёС‚Рµ..."
                        options_text.append(txt)
                        options_map[txt.lower()] = txt  # РљР»СЋС‡ - С‚РµРєСЃС‚ РІ РЅРёР¶РЅРµРј СЂРµРіРёСЃС‚СЂРµ

            elif text_inputs:
                question_type = "text"
                # РЎРѕС…СЂР°РЅСЏРµРј СЌР»РµРјРµРЅС‚, С‡С‚РѕР±С‹ РїРѕС‚РѕРј РІ РЅРµРіРѕ РїРёСЃР°С‚СЊ
                options_map["text_input"] = text_inputs[0]
                # РћРїС†РёР№ РЅРµС‚, РР РґРѕР»Р¶РµРЅ СЃРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ СЃР»РѕРІРѕ СЃР°Рј

            else:
                # Р’) РРЅР°С‡Рµ СЌС‚Рѕ Р Р°РґРёРѕ РёР»Рё Р§РµРєР±РѕРєСЃС‹ (РЎС‚Р°СЂР°СЏ Р»РѕРіРёРєР°)
                options_elements = q_block.find_elements(By.CSS_SELECTOR, ".answer div[class^='r']")

                for index, opt in enumerate(options_elements):
                    try:
                        # РўРµРєСЃС‚ РІР°СЂРёР°РЅС‚Р°
                        txt = opt.text.strip()
                        options_text.append(txt)

                        # РС‰РµРј РєР»СЋС‡ (a, b, c)
                        try:
                            key = opt.find_element(By.CSS_SELECTOR, ".answernumber").text.lower().strip(" .)")
                        except:
                            key = "opt_" + str(index)

                        # РС‰РµРј Input (РёРіРЅРѕСЂРёСЂСѓСЏ hidden)
                        try:
                            inp = opt.find_element(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                        except:
                            inp = opt.find_element(By.TAG_NAME, "input")

                        options_map[key] = inp

                        if question_type == "unknown":
                            question_type = inp.get_attribute("type")
                    except:
                        continue

            print(f"\nвќ“ Р’РѕРїСЂРѕСЃ ({question_type}): {q_text[:80]}...")

            # --- 4. РЎРџР РђРЁРР’РђР•Рњ РР ---
            variants_str = "\n".join(options_text)
            ai_ans = ask_ai_question(q_text, variants_str, lecture_text)

            # --- 5. РћР‘Р РђР‘РћРўРљРђ РћРўР’Р•РўРђ ---
            target_keys = []
            text_answer_clean = ""

            if question_type == 'text':
                # РћС‡РёС‰Р°РµРј РѕС‚РІРµС‚ РР РѕС‚ РєР°РІС‹С‡РµРє Рё С‚РѕС‡РµРє
                text_answer_clean = ai_ans.strip().strip('"').strip("'").strip(".")
                # РЈР±РёСЂР°РµРј РїСЂРµС„РёРєСЃС‹ РІРёРґР° "a. ", "a) ", "1. " РІ С‚РµРєСЃС‚РѕРІРѕРј РѕС‚РІРµС‚Рµ
                text_answer_clean = re.sub(r"^\s*[a-zР°-СЏ0-9]+\s*[\.\)]\s+", "", text_answer_clean, flags=re.IGNORECASE)
                print(f"рџ¤– РР РЅР°РїРёСЃР°Р»: '{text_answer_clean}'")

            elif question_type == 'select':
                # РС‰РµРј СЃРѕРІРїР°РґРµРЅРёРµ С‚РµРєСЃС‚Р° РІ РѕРїС†РёСЏС…
                ai_lower = ai_ans.lower()
                for opt_key in options_map:
                    # Р•СЃР»Рё РѕС‚РІРµС‚ РР СЃРѕРґРµСЂР¶РёС‚СЃСЏ РІ РѕРїС†РёРё РёР»Рё РЅР°РѕР±РѕСЂРѕС‚
                    if opt_key in ai_lower or ai_lower in opt_key:
                        target_keys = [options_map[opt_key]]  # РЎРѕС…СЂР°РЅСЏРµРј РїРѕР»РЅС‹Р№ С‚РµРєСЃС‚ РѕРїС†РёРё
                        print(f"рџ¤– РР РІС‹Р±СЂР°Р» СЃРµР»РµРєС‚: {target_keys[0]}")
                        break
                # Fallback РґР»СЏ СЃРµР»РµРєС‚Р°
                if not target_keys and options_text:
                    target_keys = [options_text[0]]

            else:
                # Р Р°РґРёРѕ Рё Р§РµРєР±РѕРєСЃС‹ (РџР°СЂСЃРёРЅРі Р±СѓРєРІ a, b, c)
                extracted_all = extract_answers(ai_ans)

                if question_type == 'radio':
                    if extracted_all:
                        # Р‘РµСЂРµРј РџРћРЎР›Р•Р”РќР®Р® Р±СѓРєРІСѓ (РѕР±С‹С‡РЅРѕ СЌС‚Рѕ РІС‹РІРѕРґ)
                        last_key = extracted_all[-1]
                        if last_key in options_map:
                            target_keys = [last_key]
                        else:
                            # Р•СЃР»Рё РїРѕСЃР»РµРґРЅРµР№ РЅРµС‚, РёС‰РµРј Р»СЋР±СѓСЋ РїРѕРґС…РѕРґСЏС‰СѓСЋ СЃ РєРѕРЅС†Р°
                            valid_keys = [k for k in reversed(extracted_all) if k in options_map]
                            if valid_keys: target_keys = [valid_keys[0]]
                    else:
                        target_keys = []
                else:
                    # Р§РµРєР±РѕРєСЃС‹: Р±РµСЂРµРј Р’РЎР• СѓРЅРёРєР°Р»СЊРЅС‹Рµ РІР°Р»РёРґРЅС‹Рµ РєР»СЋС‡Рё
                    target_keys = list(set([k for k in extracted_all if k in options_map]))

                if target_keys:
                    print(f"рџ¤– РР РІС‹Р±СЂР°Р»: {target_keys}")
                else:
                    # Fallback РґР»СЏ РєРЅРѕРїРѕРє
                    if options_map:
                        print("рџ† РР РЅРµ РґР°Р» Р±СѓРєРІСѓ. Р’С‹Р±РёСЂР°РµРј РїРµСЂРІС‹Р№ РІР°СЂРёР°РЅС‚.")
                        target_keys = [list(options_map.keys())[0]]

            # --- 6. Р”Р•Р™РЎРўР’РР• (Р’РІРѕРґ / РљР»РёРє) ---

            if question_type == 'text':
                try:
                    inp = options_map["text_input"]
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", inp)
                    inp.clear()
                    inp.send_keys(text_answer_clean)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"вќЊ РћС€РёР±РєР° РІРІРѕРґР° С‚РµРєСЃС‚Р°: {e}")

            elif question_type == 'select':
                try:
                    # Р”Р»СЏ СЃРµР»РµРєС‚Р° target_keys С…СЂР°РЅРёС‚ РўР•РљРЎРў РѕРїС†РёРё
                    select_obj.select_by_visible_text(target_keys[0])
                    time.sleep(0.5)
                except Exception as e:
                    print(f"вќЊ РћС€РёР±РєР° РІС‹Р±РѕСЂР° РІ СЃРµР»РµРєС‚Рµ: {e}")

            else:
                # Р Р°РґРёРѕ / Р§РµРєР±РѕРєСЃ
                for key in target_keys:
                    if key in options_map:
                        el = options_map[key]
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                        if not el.is_selected():
                            driver.execute_script("arguments[0].click();", el)
                            time.sleep(0.3)

            # --- 7. РџР•Р Р•РҐРћР” Р”РђР›Р•Р• ---
            try:
                driver.find_element(By.NAME, "next").click()
            except NoSuchElementException:
                pass  # Р’РѕР·РјРѕР¶РЅРѕ, СЌС‚Рѕ РїРѕСЃР»РµРґРЅРёР№ РІРѕРїСЂРѕСЃ, Рё РїРµСЂРµС…РѕРґ РїСЂРѕРёР·РѕР№РґРµС‚ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё

        except Exception as e:
            print(f"вќЊ Р“Р»РѕР±Р°Р»СЊРЅР°СЏ РѕС€РёР±РєР° С†РёРєР»Р°: {e}")
            break

def parse_results(driver):
    """
    РџР°СЂСЃРёС‚ РёС‚РѕРіРѕРІСѓСЋ С‚Р°Р±Р»РёС†Сѓ Moodle РїРѕСЃР»Рµ Р·Р°РІРµСЂС€РµРЅРёСЏ С‚РµСЃС‚Р°.
    """
    print("\nрџ“Љ --- РРўРћР“Р РўР•РЎРўРђ ---")
    try:
        # Р–РґРµРј РїРѕСЏРІР»РµРЅРёСЏ С‚Р°Р±Р»РёС†С‹ СЃ СЂРµР·СѓР»СЊС‚Р°С‚Р°РјРё
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".quizreviewsummary"))
        )

        # 1. Р’СЂРµРјСЏ
        # РС‰РµРј h5 "Р—Р°С‚СЂР°С‡РµРЅРЅРѕРµ РІСЂРµРјСЏ" -> Р±РµСЂРµРј СЃРѕСЃРµРґР° div
        try:
            time_taken = driver.find_element(By.XPATH,
                                             "//h5[contains(., 'Р—Р°С‚СЂР°С‡РµРЅРЅРѕРµ РІСЂРµРјСЏ')]/following-sibling::div").text
            print(f"вЏ±пёЏ Р’СЂРµРјСЏ: {time_taken}")
        except:
            time_taken = "РќРµ РЅР°Р№РґРµРЅРѕ"

        # 2. Р‘Р°Р»Р»С‹
        try:
            points = driver.find_element(By.XPATH, "//h5[contains(., 'Р‘Р°Р»Р»С‹')]/following-sibling::div").text
            print(f"рџЋЇ Р‘Р°Р»Р»С‹: {points}")
        except:
            points = "-"

        # 3. РћС†РµРЅРєР°
        try:
            grade = driver.find_element(By.XPATH, "//h5[contains(., 'РћС†РµРЅРєР°')]/following-sibling::div").text
            print(f"рџЏ† РћС†РµРЅРєР°: {grade}")
        except:
            grade = "-"

        # Р›РѕРіРёСЂСѓРµРј РІ С„Р°Р№Р»
        with open(BOT_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] Р’СЂРµРјСЏ: {time_taken} | Р‘Р°Р»Р»С‹: {points} | РћС†РµРЅРєР°: {grade}\n")

    except Exception as e:
        print(f"вљ пёЏ РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ СЃС‚Р°С‚РёСЃС‚РёРєСѓ: {e}")

def submit_test(driver):
    """РћС‚РїСЂР°РІР»СЏРµС‚ С‚РµСЃС‚ РЅР° РїСЂРѕРІРµСЂРєСѓ"""
    try:
        # РС‰РµРј РєРЅРѕРїРєСѓ "РћС‚РїСЂР°РІРёС‚СЊ РІСЃС‘ Рё Р·Р°РІРµСЂС€РёС‚СЊ С‚РµСЃС‚"
        # РћРЅР° РјРѕР¶РµС‚ Р±С‹С‚СЊ РІ СЂР°Р·РЅС‹С… РјРµСЃС‚Р°С…, РёС‰РµРј РїРѕ С‚РµРєСЃС‚Сѓ
        finish_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'РћС‚РїСЂР°РІРёС‚СЊ РІСЃС‘')] | //input[@value='РћС‚РїСЂР°РІРёС‚СЊ РІСЃС‘ Рё Р·Р°РІРµСЂС€РёС‚СЊ С‚РµСЃС‚']"))
        )
        finish_btn.click()

        # РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РІ РјРѕРґР°Р»РєРµ
        modal_confirm = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-action='save']"))
        )
        modal_confirm.click()

        print("вњ… РўР•РЎРў Р—РђР’Р•Р РЁР•Рќ!")
        time.sleep(3)

        # РџРђР РЎРРњ Р Р•Р—РЈР›Р¬РўРђРў
        parse_results(driver)
        time.sleep(2)

        # Р’РѕР·РІСЂР°С‚ РЅР° РіР»Р°РІРЅСѓСЋ
        driver.get(url_home_page)
        time.sleep(2)

    except Exception as e:
        print(f"вљ пёЏ РћС€РёР±РєР° С„РёРЅР°Р»РёР·Р°С†РёРё (РІРѕР·РјРѕР¶РЅРѕ СѓР¶Рµ РѕС‚РїСЂР°РІР»РµРЅ): {e}\n")
        driver.get(url_home_page)

