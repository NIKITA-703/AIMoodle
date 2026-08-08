import argparse

from app.runner import run


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
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(tests_limit=args.tests, parallel_workers=args.workers)
