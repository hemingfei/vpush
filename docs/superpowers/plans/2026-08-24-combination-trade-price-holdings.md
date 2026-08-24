# 组合调仓成交价与现有持仓 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在组合调仓通知中显示接口提供的成交价，并在现金行后展示调仓后的现有股票持仓，同时兼容旧帖子和缺失字段。

**Architecture:** 组合抓取器继续复用 `cube_snapshots` 的 holdings 快照，只在 `Post.detail` 增加 `actions[*].price` 与 `holdings`。飞书、Telegram（文本和富 HTML）、企业微信分别在自己的现有组合格式化函数中读取这两个字段；价格和持仓都采用可选字段，缺失时不渲染。

**Tech Stack:** Python 3、httpx、pytest、飞书 interactive card JSON、Telegram HTML、企业微信 Markdown。

---

### Task 1: 锁定抓取器输出契约

**Files:**
- Modify: `app/fetchers/combination.py:384-459`
- Test: `tests/test_fetchers.py:352-475`

- [ ] **Step 1: Extend the fixture with a representative price and holdings assertion.**

在第一笔 `rebalancing_histories` 的贵州茅台记录中加入 `"price": 1560.5`，在抓取断言中增加：

```python
assert p.detail["actions"][1]["price"] == "1560.50"
assert p.detail["holdings"] == [
    {"name": "贵州茅台", "symbol": "SH600519", "weight": 5.2},
    {"name": "中国平安", "symbol": "SH601318", "weight": 30.0},
]
```

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `pytest tests/test_fetchers.py::test_combination_fetch_parses_rebalancing -q`

Expected: FAIL because actions do not contain `price` and post detail does not contain `holdings`.

- [ ] **Step 3: Add minimal price extraction and snapshot projection.**

在 `app/fetchers/combination.py` 中新增一个局部公共 helper：

```python
def _format_trade_price(history: dict) -> str:
    for key in ("price", "stock_price", "trade_price"):
        value = _num(history.get(key))
        if value is not None:
            return f"{value:.2f}"
    return ""
```

在构造 `actions` 时将非空结果写入 `action["price"]`；在构造 `Post.detail` 前读取最新 holdings snapshot：

```python
holdings_snapshot = self.db.get_cube_snapshot(kol["id"], "holdings") or {}
holdings_payload = holdings_snapshot.get("payload") or {}
holdings = holdings_payload.get("holdings") or []
```

并将 `"holdings": holdings` 放入 detail。不要把现金再次塞进 holdings，现金继续使用现有 `cash` 字段。

- [ ] **Step 4: Run the focused test and verify it passes.**

Run: `pytest tests/test_fetchers.py::test_combination_fetch_parses_rebalancing -q`

Expected: PASS.

- [ ] **Step 5: Add missing-price compatibility coverage.**

在 `tests/test_fetchers.py` 的组合抓取器导入中加入 `_format_trade_price`，并新增：

```python
def test_combination_trade_price_missing_is_omitted():
    assert _format_trade_price({"prev_weight": 10.0, "target_weight": 12.0}) == ""
    assert _format_trade_price({"price": "not-a-number"}) == ""
```

这固定了没有价格字段或价格不可解析时不抛错、也不生成空外的伪价格。

- [ ] **Step 6: Run all fetcher tests and commit.**

Run: `pytest tests/test_fetchers.py -q`

Expected: PASS.

```bash
git add app/fetchers/combination.py tests/test_fetchers.py
git commit -m "feat: include combination trade prices and holdings"
```

---

### Task 2: 更新三种推送渠道的组合卡片

**Files:**
- Modify: `app/notifiers/feishu.py:156-235`
- Modify: `app/notifiers/telegram.py:101-134`
- Modify: `app/notifiers/telegram_rich.py:179-214`
- Modify: `app/notifiers/wecom.py:48-82`
- Test: `tests/test_format.py:80-125`
- Test: `tests/test_telegram_rich.py:28-65`

- [ ] **Step 1: Extend notifier fixtures with optional price and holdings.**

在 `make_combination_post()` 的第一个 action 加入 `"price": "1560.50"`，detail 加入：

```python
"holdings": [
    {"name": "贵州茅台", "symbol": "SH600519", "weight": 12.5},
    {"name": "天华新能", "symbol": "SZ300390", "weight": 20.0},
],
```

在测试中分别断言纯文本、富 HTML 和飞书 card 含有 `成交价 1560.50`、`现有持仓`、股票代码和权重。

- [ ] **Step 2: Run notifier tests and verify the new assertions fail.**

Run: `pytest tests/test_format.py::test_combination_text_layout tests/test_format.py::test_combination_feishu_card tests/test_telegram_rich.py::test_combination_rich_uses_tables -q`

Expected: FAIL because current formatters ignore price and holdings.

- [ ] **Step 3: Implement optional fields in plain text and Markdown.**

`app/notifiers/telegram.py` 和 `app/notifiers/wecom.py` 每个 action 的仓位行后追加：

```python
price = a.get("price") or ""
if price:
    lines.append(f"成交价 {price}")
```

所有 action 结束后、现金之前或之后固定追加：

```python
valid_holdings = [
    h for h in (detail.get("holdings") or [])
    if isinstance(h, dict) and h.get("name") and h.get("weight") is not None
]
if valid_holdings:
    lines.append("现有持仓")
    lines.extend(
        f"{h['name']}（{h.get('symbol') or ''}） {h['weight']}%"
        for h in valid_holdings
    )
```

只渲染 dict 且名称/权重存在的持仓，避免异常快照破坏通知。

- [ ] **Step 4: Implement optional fields in the Feishu card.**

在每个 action 的 Markdown 内容中，把价格作为第二行追加：

```python
price_line = f"\n成交价 {price}" if price else ""
content = f"{icon} **{a_type}** {stock_text}\n{prev} → {target}{price_line}"
```

现金后增加一个 `div` 元素：

```python
valid_holdings = [
    h for h in (detail.get("holdings") or [])
    if isinstance(h, dict) and h.get("name") and h.get("weight") is not None
]
if valid_holdings:
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "**现有持仓**\n" + "\n".join(
                f"{h['name']}（{h.get('symbol') or ''}） {h['weight']}%"
                for h in valid_holdings
            ),
        },
    })
```

当过滤后没有有效持仓时不追加该元素。

- [ ] **Step 5: Update Telegram rich HTML table.**

在 `build_combination_rich_html` 中先过滤有效 action 和 holding：

```python
holdings = detail.get("holdings") or []
priced_actions = [a for a in actions if isinstance(a, dict) and a.get("price")]
headers = ["操作", "标的", "仓位"] + (["成交价"] if priced_actions else [])
rows = []
for a in actions:
    row = [
        action_label(str(a.get("type") or "调整")),
        f"{a.get('stock') or ''}（{a.get('symbol') or ''}）",
        f"{a.get('prev') or '0.0%'} → {a.get('target') or '0.0%'}",
    ]
    if priced_actions:
        row.append(str(a.get("price") or "—"))
    rows.append(row)
if rows:
    parts.append(_table(headers, rows, striped=True))
```

若 `holdings` 中存在有效条目，追加：

```python
holding_rows = [
    [str(h["name"]), str(h.get("symbol") or ""), f"{h['weight']}%"]
    for h in holdings
    if isinstance(h, dict) and h.get("name") and h.get("weight") is not None
]
if holding_rows:
    parts.append(_table(["名称", "代码", "仓位"], holding_rows, caption="现有持仓", striped=True))
```

- [ ] **Step 6: Run the notifier tests and compatibility tests.**

Run:

```bash
pytest tests/test_format.py::test_combination_text_layout tests/test_format.py::test_combination_feishu_card tests/test_telegram_rich.py::test_combination_rich_uses_tables -q
pytest tests/test_format.py tests/test_telegram_rich.py -q
```

Expected: PASS, including old detail fixtures without price/holdings.

- [ ] **Step 7: Commit channel changes.**

```bash
git add app/notifiers/feishu.py app/notifiers/telegram.py app/notifiers/telegram_rich.py app/notifiers/wecom.py tests/test_format.py tests/test_telegram_rich.py
git commit -m "feat: show combination prices and current holdings"
```

---

### Task 3: Full regression and final review

**Files:**
- Test: `tests/test_fetchers.py`
- Test: `tests/test_format.py`
- Test: `tests/test_telegram_rich.py`
- Test: `tests/test_miniprogram_timeline.py`

- [ ] **Step 1: Run the targeted regression set.**

Run:

```bash
pytest tests/test_fetchers.py tests/test_format.py tests/test_telegram_rich.py tests/test_miniprogram_timeline.py -q
```

Expected: PASS.

- [ ] **Step 2: Inspect the diff for scope and compatibility.**

Run: `git diff HEAD~2..HEAD --stat && git diff HEAD~2..HEAD --check`

Expected: only the combination fetcher, three notifier implementations, their tests, and the approved design/plan docs are changed; `git diff --check` prints nothing.

- [ ] **Step 3: Run the broader test suite.**

Run: `pytest -q`

Expected: PASS. If unrelated existing failures occur, record the exact failing tests and do not claim a clean suite.

- [ ] **Step 4: Verify the final working tree.**

Run: `git status --short`

Expected: no unintended files are modified; pre-existing untracked files remain untouched.
