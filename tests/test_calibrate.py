"""校准接口的单元测试（使用 FastAPI TestClient）。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BASE_PAYLOAD = {
    "anchors": [
        {"source_ms": 1000, "target_ms": 500},
        {"source_ms": 5000, "target_ms": 4500},
        {"source_ms": 9000, "target_ms": 7000},
    ],
    "segments": [
        {"start_ms": 1000, "end_ms": 3000, "text": "第一段"},
        {"start_ms": 4500, "end_ms": 5500, "text": "跨锚点片段"},
        {"start_ms": 7000, "end_ms": 9000, "text": "第三段"},
    ],
}


def test_calibrate_success():
    resp = client.post("/api/v1/calibrate", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    segments = resp.json()["segments"]
    # 保持输入顺序
    assert [s["index"] for s in segments] == [0, 1, 2]
    # 第一段：1000->500, 3000->2500（第一区间 1:1 斜率）
    assert segments[0]["start_ms"] == 500
    assert segments[0]["end_ms"] == 2500
    assert segments[0]["text"] == "第一段"
    # 跨锚点：4500 在第一区间 -> 4000；5500 在第二区间 -> 4812.5 -> 4813
    assert segments[1]["start_ms"] == 4000
    assert segments[1]["end_ms"] == 4813
    # 第三段：7000->5750, 9000->7000
    assert segments[2]["start_ms"] == 5750
    assert segments[2]["end_ms"] == 7000


def test_rounding_half_up():
    payload = {
        "anchors": [
            {"source_ms": 0, "target_ms": 0},
            {"source_ms": 3, "target_ms": 1},
        ],
        "segments": [{"start_ms": 0, "end_ms": 2, "text": "x"}],
    }
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 200
    seg = resp.json()["segments"][0]
    # 2 * 1/3 = 0.666... -> 1
    assert seg["start_ms"] == 0
    assert seg["end_ms"] == 1


def test_anchors_must_be_strictly_increasing():
    payload = {
        "anchors": [
            {"source_ms": 1000, "target_ms": 500},
            {"source_ms": 1000, "target_ms": 600},
        ],
        "segments": [{"start_ms": 1000, "end_ms": 1000, "text": "x"}],
    }
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 422

    payload["anchors"] = [
        {"source_ms": 1000, "target_ms": 500},
        {"source_ms": 2000, "target_ms": 500},
    ]
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 422


def test_at_least_two_anchors():
    payload = {
        "anchors": [{"source_ms": 0, "target_ms": 0}],
        "segments": [{"start_ms": 0, "end_ms": 1, "text": "x"}],
    }
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 422


def test_segment_out_of_anchor_range_reports_index():
    payload = {
        "anchors": [
            {"source_ms": 1000, "target_ms": 0},
            {"source_ms": 5000, "target_ms": 4000},
        ],
        "segments": [
            {"start_ms": 1000, "end_ms": 2000, "text": "ok"},
            {"start_ms": 4500, "end_ms": 6000, "text": "bad"},
        ],
    }
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "segment_out_of_anchor_range"
    assert detail["segment_index"] == 1


def test_non_positive_duration_reports_index():
    payload = {
        "anchors": [
            {"source_ms": 0, "target_ms": 0},
            {"source_ms": 5000, "target_ms": 4000},
        ],
        "segments": [{"start_ms": 2000, "end_ms": 2000, "text": "zero"}],
    }
    resp = client.post("/api/v1/calibrate", json=payload)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "non_positive_duration"
    assert detail["segment_index"] == 0


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
