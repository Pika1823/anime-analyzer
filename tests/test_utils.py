from pathlib import Path
from datetime import date
from unittest.mock import patch
import pandas as pd
import pytest
from utils import get_logger, is_weekly_run_day, load_csv, save_csv


def test_get_logger_returns_named_logger():
    logger = get_logger("test_module")
    assert logger.name == "test_module"


def test_is_weekly_run_day_returns_true_on_monday():
    # date.today() が月曜（weekday=0）を返すようにモック
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 0
        assert is_weekly_run_day() is True


def test_is_weekly_run_day_returns_false_on_wednesday():
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 2
        assert is_weekly_run_day() is False


def test_is_weekly_run_day_force_run_env(monkeypatch):
    """FORCE_RUN=true の場合、曜日にかかわらず True を返すことを確認する。"""
    monkeypatch.setenv("FORCE_RUN", "true")
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 2  # 水曜
        assert is_weekly_run_day() is True


def test_is_weekly_run_day_force_run_false(monkeypatch):
    """FORCE_RUN=false の場合、通常の曜日判定が行われることを確認する。"""
    monkeypatch.setenv("FORCE_RUN", "false")
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 2  # 水曜
        assert is_weekly_run_day() is False


def test_is_weekly_run_day_custom_weekday():
    with patch("utils.date") as mock_date:
        mock_date.today.return_value.weekday.return_value = 3  # 木曜
        assert is_weekly_run_day(weekday=3) is True
        assert is_weekly_run_day(weekday=0) is False


def test_load_csv_returns_empty_df_when_file_missing(tmp_path):
    result = load_csv(tmp_path / "missing.csv")
    assert isinstance(result, pd.DataFrame)
    assert result.empty


def test_save_and_load_csv_roundtrip(tmp_path):
    df = pd.DataFrame({"ncode": ["N001", "N002"], "title": ["A", "B"]})
    path = tmp_path / "test.csv"
    save_csv(df, path)
    loaded = load_csv(path)
    pd.testing.assert_frame_equal(df, loaded)


def test_save_csv_creates_parent_directory(tmp_path):
    df = pd.DataFrame({"a": [1]})
    path = tmp_path / "subdir" / "nested.csv"
    save_csv(df, path)
    assert path.exists()
