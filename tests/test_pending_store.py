import pytest

from crate_builder import pending_store


@pytest.fixture(autouse=True)
def isolated_pending_store(tmp_path, monkeypatch):
    monkeypatch.setattr(pending_store, "STORE_PATH", str(tmp_path / "pending_events.json"))


def test_get_cached_events_empty_by_default():
    assert pending_store.get_cached_events() == []


def test_first_poll_marks_everything_new():
    events = [
        {
            "code": "ABC123",
            "couple": "Alex & Sam",
            "date": "2026-09-12",
            "songs": [{"moment": "First Dance", "song": "Perfect - Ed Sheeran"}],
        }
    ]
    tagged = pending_store.update_from_poll(events)

    assert tagged[0]["songs"][0]["is_new"] is True
    assert pending_store.get_cached_events() == tagged


def test_second_poll_with_same_songs_marks_nothing_new():
    events = [
        {
            "code": "ABC123",
            "couple": "Alex & Sam",
            "date": "2026-09-12",
            "songs": [{"moment": "First Dance", "song": "Perfect - Ed Sheeran"}],
        }
    ]
    pending_store.update_from_poll(events)
    tagged = pending_store.update_from_poll(events)

    assert tagged[0]["songs"][0]["is_new"] is False


def test_poll_flags_only_the_newly_added_song():
    first = [
        {
            "code": "ABC123",
            "couple": "Alex & Sam",
            "date": "2026-09-12",
            "songs": [{"moment": "First Dance", "song": "Perfect - Ed Sheeran"}],
        }
    ]
    pending_store.update_from_poll(first)

    second = [
        {
            "code": "ABC123",
            "couple": "Alex & Sam",
            "date": "2026-09-12",
            "songs": [
                {"moment": "First Dance", "song": "Perfect - Ed Sheeran"},
                {"moment": "Cake Cutting", "song": "Sugar - Maroon 5"},
            ],
        }
    ]
    tagged = pending_store.update_from_poll(second)

    songs_by_moment = {s["moment"]: s["is_new"] for s in tagged[0]["songs"]}
    assert songs_by_moment["First Dance"] is False
    assert songs_by_moment["Cake Cutting"] is True


def test_different_events_tracked_independently():
    pending_store.update_from_poll(
        [{"code": "EVENT1", "couple": "A & B", "date": None, "songs": [{"moment": "M1", "song": "S1"}]}]
    )
    tagged = pending_store.update_from_poll(
        [{"code": "EVENT2", "couple": "C & D", "date": None, "songs": [{"moment": "M1", "song": "S1"}]}]
    )

    # EVENT2 is new to the store, even though the exact (moment, song) pair
    # was already seen under EVENT1 — dedup is scoped per event.
    assert tagged[0]["songs"][0]["is_new"] is True
