"""访谈字幕时间轴校准 API.

客户端提交以原录音毫秒计时的字幕片段，以及至少两组
“原时间 -> 成片时间”同步锚点；服务端在相邻锚点间做线性换算，
把每段字幕的起止时间映射到成片时间轴。
"""

from __future__ import annotations

from bisect import bisect_right
from decimal import ROUND_HALF_UP, Decimal
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

app = FastAPI(
    title="访谈字幕时间轴校准 API",
    version="1.0.0",
    description="根据同步锚点将原录音时间轴上的字幕线性换算到成片时间轴。",
)


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #
class Anchor(BaseModel):
    """一组同步锚点：原录音时间 -> 成片时间（均为毫秒）。"""

    source_ms: float = Field(..., ge=0, description="原录音时间（毫秒）")
    target_ms: float = Field(..., ge=0, description="成片时间（毫秒）")


class SegmentIn(BaseModel):
    """输入字幕片段，时间为原录音毫秒。"""

    start_ms: float = Field(..., ge=0, description="片段开始（原录音毫秒）")
    end_ms: float = Field(..., ge=0, description="片段结束（原录音毫秒）")
    text: str = Field(..., description="字幕文字")


class SegmentOut(BaseModel):
    """校准后的字幕片段，时间为成片毫秒（四舍五入到整数）。"""

    index: int = Field(..., description="在输入 segments 中的位置（从 0 开始）")
    start_ms: int
    end_ms: int
    text: str


class CalibrateRequest(BaseModel):
    anchors: List[Anchor] = Field(..., min_length=2, description="至少两组同步锚点")
    segments: List[SegmentIn] = Field(..., min_length=1, description="至少一条字幕片段")

    @model_validator(mode="after")
    def anchors_strictly_increasing(self) -> "CalibrateRequest":
        for i in range(1, len(self.anchors)):
            prev, cur = self.anchors[i - 1], self.anchors[i]
            if cur.source_ms <= prev.source_ms:
                raise ValueError(
                    f"anchors[{i}].source_ms={cur.source_ms} 必须大于 "
                    f"anchors[{i - 1}].source_ms={prev.source_ms}（source_ms 需严格递增）"
                )
            if cur.target_ms <= prev.target_ms:
                raise ValueError(
                    f"anchors[{i}].target_ms={cur.target_ms} 必须大于 "
                    f"anchors[{i - 1}].target_ms={prev.target_ms}（target_ms 需严格递增）"
                )
        return self


class CalibrateResponse(BaseModel):
    segments: List[SegmentOut]


# --------------------------------------------------------------------------- #
# 换算逻辑
# --------------------------------------------------------------------------- #
def round_half_up_ms(value: float) -> int:
    """四舍五入到整数毫秒（ROUND_HALF_UP）。"""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TimelineConverter:
    """在相邻锚点间做线性插值，把原录音时间换算为成片时间。"""

    def __init__(self, anchors: List[Anchor]) -> None:
        self.sources = [a.source_ms for a in anchors]
        self.targets = [a.target_ms for a in anchors]

    @property
    def coverage(self) -> tuple[float, float]:
        """锚点覆盖的原录音时间范围 [下界, 上界]。"""
        return self.sources[0], self.sources[-1]

    def convert(self, t: float) -> float:
        """线性换算单个时间点（调用前需保证 t 在覆盖范围内）。"""
        i = bisect_right(self.sources, t) - 1
        i = min(max(i, 0), len(self.sources) - 2)
        s1, s2 = self.sources[i], self.sources[i + 1]
        d1, d2 = self.targets[i], self.targets[i + 1]
        return d1 + (t - s1) * (d2 - d1) / (s2 - s1)


def _segment_error(status_code: int, error: str, index: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "segment_index": index, "message": message},
    )


# --------------------------------------------------------------------------- #
# 路由
# --------------------------------------------------------------------------- #
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/calibrate", response_model=CalibrateResponse)
def calibrate(req: CalibrateRequest) -> CalibrateResponse:
    converter = TimelineConverter(req.anchors)
    lo, hi = converter.coverage

    results: List[SegmentOut] = []
    for idx, seg in enumerate(req.segments):
        # 字幕必须落在锚点覆盖范围内
        if seg.start_ms < lo or seg.end_ms > hi:
            raise _segment_error(
                422,
                "segment_out_of_anchor_range",
                idx,
                f"第 {idx} 段字幕 [{seg.start_ms}, {seg.end_ms}]ms "
                f"超出锚点覆盖范围 [{lo}, {hi}]ms",
            )

        # 跨锚点的片段：两个端点各自按所在区间分别线性换算
        start = converter.convert(seg.start_ms)
        end = converter.convert(seg.end_ms)

        # 换算后时长必须为正
        if end - start <= 0:
            raise _segment_error(
                422,
                "non_positive_duration",
                idx,
                f"第 {idx} 段字幕换算后时长非正："
                f"[{seg.start_ms}, {seg.end_ms}]ms -> [{start}, {end}]ms",
            )

        results.append(
            SegmentOut(
                index=idx,
                start_ms=round_half_up_ms(start),
                end_ms=round_half_up_ms(end),
                text=seg.text,
            )
        )

    return CalibrateResponse(segments=results)
