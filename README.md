# 访谈字幕时间轴校准 API

将按**原录音毫秒**计时的字幕片段，依据客户端提供的“原时间 → 成片时间”同步锚点，线性换算到**成片时间轴**。

- 至少提交 2 组锚点，服务端校验两列锚点（`source_ms`、`target_ms`）均严格递增；
- 相邻锚点之间做线性插值，每段字幕的起止时间分别换算（跨锚点的片段，两个端点各自按所在区间换算）；
- 字幕超出锚点覆盖范围，或换算后时长非正时，返回带片段位置（`segment_index`）的错误；
- 成功时按输入顺序返回四舍五入到整数毫秒的起止时间及原字幕文字。

## 快速启动（单条命令）

```bash
docker compose up --build
```

依赖安装（`pip install -r requirements.txt`）在镜像构建阶段完成，服务启动（`uvicorn`）为容器启动命令，无需额外手工步骤。

## 配置

| 环境变量   | 默认值 | 说明                       |
| ---------- | ------ | -------------------------- |
| `APP_PORT` | `8000` | 宿主机暴露端口（容器内固定 8000） |

示例：`APP_PORT=9000 docker compose up --build`

## 服务地址

| 用途           | 地址                                   |
| -------------- | -------------------------------------- |
| 校准接口       | `POST http://localhost:8000/api/v1/calibrate` |
| 交互式 API 文档 | `http://localhost:8000/docs`（Swagger UI） |
| 健康检查       | `GET http://localhost:8000/healthz`    |

## API 说明

### 请求体

```json
{
  "anchors": [
    { "source_ms": 1000, "target_ms": 500 },
    { "source_ms": 5000, "target_ms": 4500 },
    { "source_ms": 9000, "target_ms": 7000 }
  ],
  "segments": [
    { "start_ms": 1000, "end_ms": 3000, "text": "第一段" },
    { "start_ms": 4500, "end_ms": 5500, "text": "跨锚点片段" }
  ]
}
```

- `anchors`：至少 2 组；`source_ms`（原录音毫秒）与 `target_ms`（成片毫秒）两列都必须严格递增；
- `segments`：至少 1 段；`start_ms` / `end_ms` 为原录音毫秒，`text` 为字幕原文。

### 成功响应 `200`

按输入顺序返回，`index` 为片段在输入中的位置，时间为四舍五入后的成片整数毫秒：

```json
{
  "segments": [
    { "index": 0, "start_ms": 500, "end_ms": 2500, "text": "第一段" },
    { "index": 1, "start_ms": 4000, "end_ms": 4813, "text": "跨锚点片段" }
  ]
}
```

### 错误响应 `422`

字幕超出锚点覆盖范围，或换算后时长非正时，返回带片段位置的错误：

```json
{
  "detail": {
    "error": "segment_out_of_anchor_range",
    "segment_index": 1,
    "message": "第 1 段字幕 [4500.0, 6000.0]ms 超出锚点覆盖范围 [1000.0, 5000.0]ms"
  }
}
```

| `error`                        | 含义                                   |
| ------------------------------ | -------------------------------------- |
| `segment_out_of_anchor_range`  | 片段起止时间超出锚点覆盖范围           |
| `non_positive_duration`        | 换算后片段时长非正                     |

锚点数量不足、锚点未严格递增、字段缺失/非法等请求体问题同样返回 `422`，由请求校验层给出具体字段位置。

### 调用示例

```bash
curl -X POST http://localhost:8000/api/v1/calibrate \
  -H 'Content-Type: application/json' \
  -d '{
    "anchors": [
      {"source_ms": 1000, "target_ms": 500},
      {"source_ms": 5000, "target_ms": 4500}
    ],
    "segments": [
      {"start_ms": 1000, "end_ms": 3000, "text": "第一段"}
    ]
  }'
```

## 本地开发（不使用 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

运行测试：

```bash
pip install pytest httpx
pytest tests/ -q
```

## 项目结构

```
app/main.py          # FastAPI 应用：模型校验、线性换算、路由
requirements.txt     # Python 依赖
Dockerfile           # 镜像构建：安装依赖 + 启动 uvicorn
docker-compose.yml   # 单服务编排，APP_PORT 可配
tests/test_calibrate.py  # 单元测试
```
