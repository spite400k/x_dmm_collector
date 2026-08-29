from utils.weekly_ranking_selection import (
    RANKING_MAX_FUTURE,
    RANKING_MAX_RELEASED_BEFORE_FUTURE,
    RANKING_TOTAL,
    merge_ranking_rows,
)


def _row(content_id: str, score: float = 10.0) -> dict:
    return {
        "content_id": content_id,
        "title": content_id,
        "final_score": score,
        "review_count": 5,
        "avg_rating": 4.0,
    }


def test_merge_ranking_rows_keeps_released_and_one_future():
    released = [_row(f"released-{i}", 100 - i) for i in range(19)]
    future = _row("future-1", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 20
    assert rows[-1]["content_id"] == "future-1"
    assert sum(1 for row in rows if row["content_id"].startswith("future-")) == 1


def test_merge_ranking_rows_skips_duplicate_future():
    released = [_row(f"released-{i}") for i in range(19)]
    future = _row("released-0", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 19
    assert rows.count(future) == 0


def test_merge_ranking_rows_limits_released_before_future():
    released = [_row(f"released-{i}") for i in range(25)]
    future = _row("future-1", 0)

    rows = merge_ranking_rows(released, future)

    assert len(rows) == 20
    assert rows[-1]["content_id"] == "future-1"
    assert len([row for row in rows if row["content_id"].startswith("released-")]) == 19


def test_merge_ranking_rows_without_future():
    released = [_row(f"released-{i}") for i in range(10)]

    rows = merge_ranking_rows(released, None)

    assert len(rows) == 10


def test_ranking_constants():
    assert RANKING_MAX_RELEASED_BEFORE_FUTURE + RANKING_MAX_FUTURE == RANKING_TOTAL
