import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

from app.models import QuizRequirements


@dataclass
class ReviewOption:
    key: str
    text: str
    checked: bool = False
    correct: Optional[bool] = None


@dataclass
class QuestionReview:
    question_id: str
    question_text: str
    question_type: str
    score: Optional[float]
    max_score: Optional[float]
    options: list[ReviewOption] = field(default_factory=list)
    text_answer: str = ""
    status: str = "unknown"

    @property
    def selected_options(self):
        return [option for option in self.options if option.checked]


@dataclass
class ReviewSummary:
    score: Optional[float] = None
    max_score: Optional[float] = None
    grade_percent: Optional[float] = None
    time_taken: str = "Не найдено"


def parse_number(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_fraction(text):
    if not text:
        return None, None

    match = re.search(r"([\d.,]+)\s*(?:/|из)\s*([\d.,]+)", text, flags=re.IGNORECASE)
    if not match:
        return None, None
    return parse_number(match.group(1)), parse_number(match.group(2))


def parse_quiz_requirements(html, course_id="", quiz_id=""):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    pass_grade = None
    pass_match = re.search(r"Проходная оценка:\s*([\d.,]+)(?:\s+из\s+([\d.,]+))?", page_text)
    if pass_match:
        value = parse_number(pass_match.group(1))
        maximum = parse_number(pass_match.group(2)) if pass_match.group(2) else 100.0
        if value is not None and maximum:
            pass_grade = value / maximum * 100.0

    allowed_attempts = None
    attempts_match = re.search(r"Разрешено попыток:\s*(\d+)", page_text)
    if attempts_match:
        allowed_attempts = int(attempts_match.group(1))

    attempt_numbers = []
    for heading in soup.find_all(["h3", "h4", "h5"]):
        match = re.fullmatch(r"Попытка\s+(\d+)", heading.get_text(" ", strip=True))
        if match:
            attempt_numbers.append(int(match.group(1)))

    continue_pattern = re.compile(r"Продолжить (?:текущую|последнюю) попытку", re.IGNORECASE)
    has_current_attempt = any(
        continue_pattern.search(tag.get_text(" ", strip=True) or tag.get("value") or "")
        for tag in soup.find_all(["button", "input"])
    )

    if has_current_attempt and attempt_numbers:
        attempt_number = max(attempt_numbers)
    elif attempt_numbers:
        attempt_number = max(attempt_numbers) + 1
    else:
        attempt_number = 1

    return QuizRequirements(
        pass_grade=pass_grade,
        allowed_attempts=allowed_attempts,
        attempt_number=attempt_number,
        course_id=str(course_id or ""),
        quiz_id=str(quiz_id or ""),
    )


def parse_review_summary(html):
    soup = BeautifulSoup(html, "html.parser")

    def value_after_title(title):
        heading = soup.find(
            lambda tag: tag.name in {"h5", "div"}
            and tag.get_text(" ", strip=True).lower() == title.lower()
        )
        if not heading:
            return ""
        sibling = heading.find_next_sibling()
        return sibling.get_text(" ", strip=True) if sibling else ""

    points_text = value_after_title("Баллы")
    grade_text = value_after_title("Оценка")
    time_taken = value_after_title("Затраченное время") or "Не найдено"

    score, max_score = parse_fraction(points_text)
    grade, grade_max = parse_fraction(grade_text)
    grade_percent = None
    if grade is not None and grade_max:
        grade_percent = grade / grade_max * 100.0

    return ReviewSummary(
        score=score,
        max_score=max_score,
        grade_percent=grade_percent,
        time_taken=time_taken,
    )


def parse_question_reviews(html):
    soup = BeautifulSoup(html, "html.parser")
    reviews = []
    navigation_statuses = _navigation_statuses(soup)

    for block in soup.select(".que"):
        qtext = block.select_one(".qtext")
        if not qtext:
            continue

        question_type = _detect_question_type(block)
        score, max_score = parse_fraction(_text_of(block.select_one(".grade")))
        question_id = _extract_question_id(block)
        options = []
        text_answer = ""

        if question_type == "text":
            input_el = block.select_one("input[type='text']")
            if input_el:
                text_answer = (input_el.get("value") or "").strip()
        elif question_type == "select":
            for index, option in enumerate(block.select("select option")):
                if not option.has_attr("selected"):
                    continue
                text = option.get_text(" ", strip=True)
                options.append(ReviewOption(str(index), text, True))
        else:
            for index, option_block in enumerate(block.select(".answer div[class^='r']")):
                input_el = option_block.select_one("input")
                if not input_el:
                    continue
                number = option_block.select_one(".answernumber")
                key = _clean_option_key(_text_of(number)) or f"opt_{index}"
                text = option_block.get_text(" ", strip=True)
                options.append(
                    ReviewOption(
                        key,
                        text,
                        input_el.has_attr("checked"),
                        _option_correctness(option_block),
                    )
                )

        status = navigation_statuses.get(block.get("id") or "", _block_status(block))
        if status == "unknown":
            status = _status_from_score(score, max_score)

        reviews.append(
            QuestionReview(
                question_id=question_id,
                question_text=qtext.get_text(" ", strip=True),
                question_type=question_type,
                score=score,
                max_score=max_score,
                options=options,
                text_answer=text_answer,
                status=status,
            )
        )

    return reviews


def _extract_question_id(block):
    post_data = block.select_one(".questionflagpostdata")
    if post_data:
        parsed = parse_qs(post_data.get("value") or "")
        qids = parsed.get("qid") or []
        if qids:
            return str(qids[0])

    for input_el in block.select("input[value*='qid=']"):
        match = re.search(r"(?:^|&)qid=(\d+)", input_el.get("value") or "")
        if match:
            return match.group(1)

    return ""


def _detect_question_type(block):
    if block.select_one("input[type='text']"):
        return "text"
    if block.select_one("select"):
        return "select"
    if block.select_one("input[type='checkbox']"):
        return "checkbox"
    if block.select_one("input[type='radio']"):
        return "radio"
    return "unknown"


def _clean_option_key(text):
    return (text or "").lower().strip(" .)")


def _option_correctness(option_block):
    classes = set(option_block.get("class") or [])
    if "incorrect" in classes:
        return False
    if "correct" in classes:
        return True

    marker = option_block.select_one("[aria-label], [title]")
    if marker:
        label = " ".join(
            filter(None, [marker.get("aria-label", ""), marker.get("title", "")])
        ).strip().lower()
        if "неверно" in label:
            return False
        if "верно" in label:
            return True
    return None


def _navigation_statuses(soup):
    statuses = {}
    for button in soup.select("a.qnbutton[href^='#question-']"):
        target = (button.get("href") or "").lstrip("#")
        if target:
            statuses[target] = _status_from_classes(button.get("class") or [])
    return statuses


def _block_status(block):
    return _status_from_classes(block.get("class") or [])


def _status_from_classes(classes):
    classes = set(classes)
    if "partiallycorrect" in classes:
        return "partial"
    if "notanswered" in classes:
        return "not_answered"
    if "incorrect" in classes:
        return "incorrect"
    if "correct" in classes:
        return "correct"
    return "unknown"


def _status_from_score(score, max_score):
    if score is None or max_score is None or max_score <= 0:
        return "unknown"
    if abs(score - max_score) < 1e-9:
        return "correct"
    if abs(score) < 1e-9:
        return "incorrect"
    return "partial"


def _text_of(tag):
    return tag.get_text(" ", strip=True) if tag else ""
