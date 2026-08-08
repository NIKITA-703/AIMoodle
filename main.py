import argparse

from app.runner import run
from app.stats import print_question_analysis


def _positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("значение должно быть не меньше 1")
    return number


def parse_args():
    parser = argparse.ArgumentParser(description="MoodleBot")
    parser.add_argument(
        "--workers",
        type=_positive_int,
        choices=range(1, 5),
        help="число разных курсов, обрабатываемых одновременно (1-4)",
    )
    parser.add_argument(
        "--tests",
        type=_positive_int,
        help="общий максимум отправленных попыток за запуск",
    )
    parser.add_argument(
        "--stats-report",
        "--stats",
        action="store_true",
        help="показать анализ накопленных ответов без запуска браузера",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.stats_report:
        print_question_analysis()
    else:
        run(tests_limit=args.tests, parallel_workers=args.workers)
