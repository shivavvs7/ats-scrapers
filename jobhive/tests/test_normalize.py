"""Test the parquet normalization helper.

Regression test for the bug discovered on the first real upload: concatenating
per-ATS CSVs produced an `ats_id` column with mixed int/str values, which
pyarrow refuses to convert.
"""

from __future__ import annotations

import pandas as pd

from jobhive.storage.publisher import _normalize_for_parquet


def test_object_columns_become_string_dtype() -> None:
    df = pd.DataFrame({"ats_id": [1, "abc", 2.5, None], "title": ["X", "Y", "Z", "W"]})
    out = _normalize_for_parquet(df)
    assert str(out["ats_id"].dtype) == "string"
    assert str(out["title"].dtype) == "string"


def test_numeric_columns_are_left_alone() -> None:
    df = pd.DataFrame({"salary_min": [100_000, 200_000], "lat": [37.7, 40.0]})
    out = _normalize_for_parquet(df)
    assert pd.api.types.is_integer_dtype(out["salary_min"])
    assert pd.api.types.is_float_dtype(out["lat"])


def test_mixed_int_and_string_ids_round_trip_through_parquet(tmp_path) -> None:
    pytest_arrow = __import__("importlib").util.find_spec("pyarrow")
    if pytest_arrow is None:
        return  # pyarrow optional in test env
    df = pd.DataFrame(
        {"ats_id": [1, "uuid-abc", 2], "title": ["A", "B", "C"], "company": ["x", "y", "z"]}
    )
    path = tmp_path / "out.parquet"
    _normalize_for_parquet(df).to_parquet(path, index=False)
    loaded = pd.read_parquet(path)
    assert loaded["ats_id"].tolist() == ["1", "uuid-abc", "2"]


def test_normalize_does_not_mutate_input() -> None:
    df = pd.DataFrame({"ats_id": [1, "abc"]})
    _normalize_for_parquet(df)
    assert df["ats_id"].dtype == object
