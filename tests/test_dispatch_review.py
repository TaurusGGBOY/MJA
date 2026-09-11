from types import SimpleNamespace as NS

import pytest

from agent.custom.action.dispatch_review import (
    VerifyDispatchList,
    append_overlapping_rows,
    waiting_rows,
)


def row(title, timer, y):
    return [NS(text=title, box=[110, y, 110, 25]),
            NS(text=timer, box=[115, y + 31, 110, 22])]


def test_countdowns_do_not_require_names():
    timers = [NS(text="Q03:22:17", box=[115, 176, 110, 22]),
              NS(text="03:22:19", box=[115, 311, 110, 22])]
    for names in ([], [NS(text="淬火之锋", box=[110, 145, 110, 25])],
                  [NS(text="伴火之译", box=[110, 145, 110, 25])],
                  [NS(text="unknown", box=[110, 145, 110, 25])]):
        assert waiting_rows([*timers, *names]) == [12137, 12139]


def test_an_actionable_row_below_running_rows_rejects_success():
    for pending in ("耗时:4小时", "已完成"):
        assert waiting_rows([*row("年久失修", "03:22:17", 145),
                             *row("行医布施", pending, 280)]) is None


def test_overlap_counts_each_row_once_and_rejects_ambiguous_or_missing_coverage():
    seen = [12137, 12139, 12141]
    following = [12136, 17000, 18000]
    assert append_overlapping_rows(seen, following) == [*seen, *following[1:]]
    assert append_overlapping_rows(seen, [100]) is None
    assert append_overlapping_rows([100, 100], [98, 98]) is None
    assert append_overlapping_rows(seen, [12199]) is None


def test_longest_monotonic_countdown_overlap():
    assert append_overlapping_rows([14370, 21575, 21581], [21573, 21579, 21584]) == [
        14370, 21575, 21581, 21584,
    ]


def test_morning_countdown_overlap_without_any_titles():
    assert append_overlapping_rows([14371, 14376, 21581, 21589],
                                   [14374, 21579, 21584, 21589]) == [
        14371, 14376, 21581, 21589, 21589,
    ]


def test_unreadable_or_invalid_countdowns_never_count_as_waiting():
    assert waiting_rows(row("年久失修", "unknown", 145)) is None
    assert waiting_rows(row("年久失修", "03:99:17", 145)) is None


@pytest.mark.parametrize("names", ["original", "missing", "unrelated"])
def test_native_action_requires_header_count_and_complete_overlapping_coverage(monkeypatch, names):
    monkeypatch.setattr("agent.custom.action.dispatch_review.sleep", lambda _: None)
    pages = [
        [*row("年久失修", "03:22:17", 145), *row("行医布施", "03:22:19", 280)],
        [*row("行医布施", "03:22:17", 145), *row("剑阵加固", "03:22:20", 280)],
    ]
    if names == "missing":
        pages = [[result for result in page if ":" in result.text] for page in pages]
    elif names == "unrelated":
        for index, page in enumerate(pages):
            for result in page:
                if ":" not in result.text:
                    result.text = f"unreadable-name-{index}-{result.box[1]}"
    for total, expected in ((3, True), (4, False), (1, False)):
        calls = []
        page_index = [-1]
        ok = NS(wait=lambda: NS(status=NS(succeeded=True)))

        def capture():
            page_index[0] = min(page_index[0] + 1, 1)
            return ok

        controller = NS(cached_image="native-frame", post_screencap=capture,
                        post_swipe=lambda *args: calls.append(args) or ok)

        def recognize(name, _frame):
            if name == "0742-英雄派遣-英雄-派遣-页面":
                return NS(hit=True)
            if name == "英雄派遣-列表-计数":
                return NS(filtered_results=[NS(text=f"任务:{total}/12"), NS(text="已完成:0")])
            return NS(filtered_results=pages[page_index[0]])

        context = NS(tasker=NS(controller=controller), run_recognition=recognize)
        assert VerifyDispatchList().run(context, NS()) is expected
        assert len(calls) <= 8
