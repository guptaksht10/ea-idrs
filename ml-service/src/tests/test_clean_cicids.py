import json
import numpy as np
import pandas as pd
from src.config import settings
from src.preprocessing import clean_cicids


def test_cleaning_accepts_traffic_labelling_csvs(monkeypatch, tmp_path):
    raw_dir, processed_dir = tmp_path / "raw", tmp_path / "processed"
    raw_dir.mkdir()
    monkeypatch.setattr(settings, "RAW_DATA_DIR", raw_dir)
    monkeypatch.setattr(settings, "PROCESSED_DIR", processed_dir)

    rng = np.random.default_rng(0)
    header = (
        "Flow ID, Source IP, Source Port, Destination IP, Destination Port, Protocol, "
        "Timestamp, Flow Duration, Fwd Header Length, Fwd Header Length.1, Label\n"
    )
    for filename in clean_cicids.CICIDS_FILES_ORDERED:
        lines = [header]
        for i in range(20):
            label = "Web Attack \x96 XSS" if i % 5 == 0 else "BENIGN"
            dur, hdr = rng.integers(1, 1000), rng.integers(20, 60)
            lines.append(
                f"1.2.3.4-5.6.7.8-{i},1.2.3.4,{1000 + i},5.6.7.8,{80 + i % 3},6,"
                f"3/7/2017 9:{i:02d},{dur},{hdr},{hdr},{label}\n"
            )
        lines.append(",,,,,,,,,,\n")  # blank trailing row as in TrafficLabelling
        (raw_dir / filename).write_bytes("".join(lines).encode("latin1"))

    out_path = clean_cicids.run_cleaning()

    df = pd.read_parquet(out_path)
    audit = json.loads((processed_dir / "preprocessing_audit.json").read_text(encoding="utf-8"))
    assert audit["raw_total_rows"] == 8 * 20  # blank rows removed before counting
    assert len(df) == 8 * 20
    assert not set(clean_cicids.TRAFFIC_LABELLING_ID_COLUMNS) & set(df.columns)
    assert "Destination Port" in df.columns
    assert audit["macro_class_counts"].get("WebAttack") == 8 * 4
    assert "Other" not in audit["macro_class_counts"]
