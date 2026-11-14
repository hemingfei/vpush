"""云网关 /api/mx-ingest 端到端测试（spec #14 票 #15）。

唯一 CI 接缝 = 云网关 wss 入口：进程内起真实 uvicorn 服务端挂生产 app，
用真 WebSocket 客户端连入扮演「采集器（扩展）」，断言端到端行为（配对/
认证/帧入库/幂等/跨账号去重/引擎帧丢弃/断连补传）。方向与
tests/test_mx_native_integration.py 相反：那边服务端=Mini EIO、客户端=生产
MxWsClient；这边服务端=云网关（生产 FastAPI app）、客户端=模拟扩展。

网关之下（解析层/入库/推送）已有 660+ 测试覆盖，这里只测网关可观察行为，
不重复测内部链路。
"""
import asyncio
import json
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn
import websockets

from app.config import Config
from app.main import create_app


def make_gateway(db_path=None, config=None):
    """造一个只含云网关的最小 FastAPI app + 共享 DB。

    不走完整 create_app（会拉起 NewsService/FeishuDocuments 等一堆无关
    服务）；云网关路由自包含（DB + 调度器回调），单测按需注入。
    路由注册进完整 create_app 的形态由 test_full_app_includes_gateway_route 覆盖。
    """
    from app.db import DB
    from app.services.mx_gateway import build_gateway_app

    tmp = Path(tempfile.mkdtemp())
    db = DB(db_path or (tmp / "gateway.db"))
    ingested = []

    def on_external_post(post):
        # 先入库再登记：模糊去重按 posts 表查候选，await_for 看到 ingested
        # 增长时候选必须已可查（appended-then-save 会有入库前的竞态窗口）
        post_id = db.save_post(post)
        ingested.append(post)
        return post_id

    app = build_gateway_app(db, on_external_post=on_external_post)
    return app, db, ingested


def start_server(app, host="127.0.0.1"):
    """进程内起真实 uvicorn（端口随机），返回 (port, stop_fn)。

    按本地 EIO 测试先例走真网络路径（绕开 ASGI TestClient 的 websocket
    兼容坑），与生产 uvicorn 完全同一套 ws 实现。
    """
    config = uvicorn.Config(app, host=host, port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]

    def stop():
        server.should_exit = True
        thread.join(timeout=10)

    return port, stop


async def ws_connect(port, path="/api/mx-ingest"):
    """模拟扩展侧的浏览器 WebSocket 连接（不能自定义 header，首帧认证）。"""
    return await websockets.connect(f"ws://127.0.0.1:{port}{path}")


# ---- 配对：8 位一次性配对码 → 设备密钥；错误码拒绝 ----


def test_pairing_binds_and_wrong_code_rejected():
    """正确配对码换取设备密钥且码作废；错误码被拒。"""

    async def scenario():
        app, db, _ = make_gateway()
        code = db.create_mx_pairing_code()
        port, stop = start_server(app)
        try:
            # 错误配对码：拒绝且不下发密钥
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": "00000000"}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is False, resp
            # 正确配对码：换到设备密钥
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is True, resp
                device_key = resp.get("device_key")
                assert device_key and len(device_key) >= 32, device_key
            # 同一码第二次配对：已作废
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is False, resp
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


# ---- 设备密钥认证与吊销 ----


def test_device_key_auth_and_revocation_disconnects():
    """设备密钥认证通过后收帧；未知密钥拒绝；吊销后现存连接即断、新连接拒绝。"""

    async def scenario():
        app, db, _ = make_gateway()
        port, stop = start_server(app)
        try:
            # 未知设备密钥：拒绝并断开
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "auth", "key": "f" * 64}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is False, resp
                with pytest.raises(websockets.ConnectionClosed) as ei:
                    await ws.recv()
                assert ei.value.rcvd.code == 4003

            # 配对拿真密钥，认证后保持在线
            code = db.create_mx_pairing_code()
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                device_key = json.loads(await ws.recv())["device_key"]

            live = await ws_connect(port)
            await live.send(json.dumps({"op": "auth", "key": device_key}))
            assert json.loads(await live.recv()) == {"ok": True}

            # 吊销：存量连接被网关断开（经 gateway 实例上的吊销回调，管理端接线点）
            device_id = db._rows("SELECT id FROM mx_devices")[0]["id"]
            db.revoke_mx_device(device_id)
            notify = getattr(app.state, "mx_ingest_notify_revoked", None)
            assert notify is not None
            notify(device_id)
            with pytest.raises(websockets.ConnectionClosed) as ei:
                # 等存量连接被服务端断开（吊销回调 fire-and-forget create_task）
                await asyncio.wait_for(live.recv(), timeout=5)
            assert ei.value.rcvd.code == 4003

            # 新连接用被吊销密钥：拒绝
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "auth", "key": device_key}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is False, resp
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=20))


# ---- 合法帧入库（信封 → 解析链 → posts）----

ROOM_ID = "801"


def make_room(db):
    kid = db.add_kol("mx", "房间甲", ROOM_ID)
    return db.get_kol(kid)


def room_msg_frame(msg_id, text, createtime=1700000000000):
    """实测 ground truth 帧形态：非默认 ns 带 42/msg, 前缀（2026-10-12 抓包）。"""
    payload = json.dumps(
        {"rid": int(ROOM_ID), "id": msg_id, "msg": text, "createtime": createtime},
        ensure_ascii=False,
    )
    return f'42/msg,["room_msg",{payload}]'


async def pair_and_auth(port, db):
    """走完整配对+认证流程，返回已认证的 websocket 连接。"""
    code = db.create_mx_pairing_code()
    async with await ws_connect(port) as ws:
        await ws.send(json.dumps({"op": "pair", "code": code}))
        device_key = json.loads(await ws.recv())["device_key"]
    live = await ws_connect(port)
    await live.send(json.dumps({"op": "auth", "key": device_key}))
    assert json.loads(await live.recv()) == {"ok": True}
    return live


async def await_for(condition, timeout=10.0, interval=0.05):
    """异步轮询等条件成立（服务端处理有毫秒级延迟；绝不能用 time.sleep——
    那会阻塞客户端事件循环，websockets 客户端就无法处理服务端流量）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        await asyncio.sleep(interval)
    return False


def test_legit_frame_ingests_to_post():
    """合法 ws_in 帧经现有解析链入库：真房间 + 真帧形态 → posts 落一条。"""

    async def scenario():
        app, db, ingested = make_gateway()
        make_room(db)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            frame = room_msg_frame(9001, '[{"type": "text", "msg": "早，重点看算力。"}]')
            envelope = {
                "seq": 1,
                "ts": int(time.time() * 1000),
                "account": "main",
                "type": "ws_in",
                "payload": frame,
            }
            await live.send(json.dumps(envelope, ensure_ascii=False))
            assert await await_for(lambda: len(ingested) == 1), "帧未入库"
            post = ingested[0]
            assert post.platform == "mx"
            assert post.external_id == "9001"
            assert "算力" in post.content
            # 落库可查（端到端断言以 DB 为准）
            assert await await_for(
                lambda: db.get_post_detail("mx", "9001") != {}
            ), "posts 表未查到该消息"
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- (account, seq) 幂等 ----


def test_duplicate_account_seq_is_idempotent():
    """同 (account, seq) 重复上行只入库一次：扩展断线重传/ACK 丢失安全。"""

    async def scenario():
        app, db, ingested = make_gateway()
        make_room(db)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            frame = room_msg_frame(9002, '[{"type": "text", "msg": "幂等验证"}]')
            envelope = {
                "seq": 7,
                "ts": int(time.time() * 1000),
                "account": "main",
                "type": "ws_in",
                "payload": frame,
            }
            # 同一信封连发两次（模拟断线重连补传/ACK 丢失重发）
            await live.send(json.dumps(envelope, ensure_ascii=False))
            assert await await_for(lambda: len(ingested) == 1), "首发帧未入库"
            await live.send(json.dumps(envelope, ensure_ascii=False))
            await asyncio.sleep(0.5)
            assert len(ingested) == 1, "重复 (account, seq) 不能二次入库"

            # 不同 seq 同内容：如实入库（seq 才是幂等键，内容不做幂等判重）
            envelope2 = dict(envelope, seq=8)
            await live.send(json.dumps(envelope2, ensure_ascii=False))
            assert await await_for(lambda: len(ingested) == 2), "新 seq 帧未入库"
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- 引擎帧防御性丢弃（扩展已过滤；网关收到也丢）----


def test_engine_frames_dropped_never_ingested():
    """引擎帧（2/3/0/40/41）即使上行也不进解析链、不入库不计数。"""

    async def scenario():
        app, db, ingested = make_gateway()
        make_room(db)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            for i, engine_frame in enumerate(
                ["2", "3", "0", '40/msg,{"sid":"x"}', "41", '0{"sid":"s","pingInterval":25000}']
            ):
                envelope = {
                    "seq": 100 + i,
                    "ts": int(time.time() * 1000),
                    "account": "main",
                    "type": "ws_in",
                    "payload": engine_frame,
                }
                await live.send(json.dumps(envelope))
            await asyncio.sleep(0.8)
            assert ingested == [], "引擎帧绝不能进解析链入库"
            # 生命周期事件表也不该有（引擎帧不是 lifecycle）
            events = db.list_mx_ingest_events()
            assert all(
                e["event"] not in ("http_frame",) for e in events
            ), "引擎帧不应记成 http/lifecycle 事件"
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- 跨账号模糊去重（接力重叠期）----


def test_cross_account_fuzzy_dedup_hits_and_same_account_repeat_kept():
    """跨账号同房间+时间相邻+内容相似 ≥90% 判同一条：后到者丢弃；
    同账号重复（不同消息 id）如实入库，不被误吞。"""

    async def scenario():
        app, db, ingested = make_gateway()
        make_room(db)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            now = int(time.time() * 1000)

            # 主账号先发
            await live.send(json.dumps(
                {
                    "seq": 1,
                    "ts": now,
                    "account": "main",
                    "type": "ws_in",
                    "payload": room_msg_frame(
                        1001, '[{"type": "text", "msg": "美联储十一月不降息，谨慎为主"}]', now
                    ),
                },
                ensure_ascii=False,
            ))
            assert await await_for(lambda: len(ingested) == 1), "主账号帧未入库"

            # 备用账号接力重叠期转发同一条：消息 id 不同（跨账号 id 天然不同）、
            # 内容仅空格/标点差别、时间相邻 → 模糊去重命中，后到者丢弃
            await live.send(json.dumps(
                {
                    "seq": 2,
                    "ts": now + 3000,
                    "account": "backup",
                    "type": "ws_in",
                    "payload": room_msg_frame(
                        2002, '[{"type": "text", "msg": "美联储十一月不降息, 谨慎为主!"}]', now + 3000
                    ),
                },
                ensure_ascii=False,
            ))
            await asyncio.sleep(0.8)
            assert len(ingested) == 1, "跨账号重复内容应被模糊去重丢弃"

            # 同账号真连发两条相同内容：如实入库，不适用跨账号规则
            await live.send(json.dumps(
                {
                    "seq": 3,
                    "ts": now + 6000,
                    "account": "main",
                    "type": "ws_in",
                    "payload": room_msg_frame(
                        1003, '[{"type": "text", "msg": "美联储十一月不降息，谨慎为主"}]', now + 6000
                    ),
                },
                ensure_ascii=False,
            ))
            assert await await_for(lambda: len(ingested) == 2), "同账号重复不能被模糊去重吞掉"
            assert ingested[1].external_id == "1003"
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- lifecycle 帧可查询 + 断连重连补传按序入库 ----


def test_lifecycle_events_recorded_and_reconnect_backfill_in_order():
    """lifecycle 帧入库可查询；断连重连后缓冲帧按序补传，顺序不乱。"""

    async def scenario():
        app, db, ingested = make_gateway()
        make_room(db)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)

            # lifecycle 帧：记录、可查询，不进解析链
            await live.send(json.dumps({
                "seq": 1,
                "ts": int(time.time() * 1000),
                "account": "main",
                "type": "lifecycle",
                "event": "startup",
                "detail": "扩展启动完成",
            }, ensure_ascii=False))
            assert await await_for(lambda: any(
                e["event"] == "startup" for e in db.list_mx_ingest_events()
            )), "lifecycle 事件未记录"
            assert ingested == [], "lifecycle 不能进解析链"

            # 模拟断连：关闭后扩展本地缓冲两条帧
            await live.close()
            assert await await_for(lambda: any(
                e["event"] == "disconnect" for e in db.list_mx_ingest_events()
            )), "断连事件未记录"
            buffered = []
            for seq, msg_id in ((10, 3001), (11, 3002)):
                buffered.append({
                    "seq": seq,
                    "ts": int(time.time() * 1000),
                    "account": "main",
                    "type": "ws_in",
                    "payload": room_msg_frame(
                        msg_id,
                        f'[{{"type": "text", "msg": "补传消息{msg_id}"}}]',
                        int(time.time() * 1000),
                    ),
                })

            # 重连：认证后按 seq 顺序补传缓冲帧
            live = await pair_and_auth(port, db)
            for env in buffered:
                await live.send(json.dumps(env, ensure_ascii=False))
            assert await await_for(lambda: len(ingested) == 2), "补传帧未入库"
            # 按序断言：入库顺序 = 补传顺序（seq 升序）
            assert [p.external_id for p in ingested] == ["3001", "3002"]
            # 补传帧不得被 (account, seq) 幂等窗二次吞掉（重传同 seq 的场景已由
            # 上一用例覆盖；此处验证重连后新帧正常入库）
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- 生产组装形态：完整 create_app 挂载网关路由 ----


def test_full_app_includes_gateway_route(tmp_path):
    """完整 create_app 必须注册 /api/mx-ingest websocket 路由（组装回归）。"""
    config = Config()
    config.db_path = str(tmp_path / "full.db")
    config.alerts_enabled = False
    app = create_app(config=config)
    paths = [getattr(r, "path", "") for r in app.router.routes]
    assert "/api/mx-ingest" in paths
    # 吊销反向通知回调可用（管理端接线点）
    assert callable(app.state.mx_ingest_notify_revoked)


# ---- 断连告警：延迟检查 + 阈值窗去重、阈值可配置 ----


def test_disconnect_alert_publishes_with_threshold_dedup():
    """断连超阈值仍离线 → 告警；阈值窗内重复断连不重复告警（去重窗语义）。"""

    async def scenario():
        from app.db import DB
        from app.services.mx_gateway import build_gateway_app

        tmp = Path(tempfile.mkdtemp())
        db = DB(tmp / "alert.db")
        alerts = []

        app = build_gateway_app(
            db,
            on_external_post=None,
            alert_publisher=lambda title, content: alerts.append((title, content)),
            # 阈值 1.0s（短窗可测）：断连后设备保持离线，延迟检查到期即告警；
            # 第二次断连落在去重窗内 → 不再告警。语义与生产 300s 相同，
            # 只是时长缩短（阈值参数可配置的意义所在）
            disconnect_alert_seconds=1.0,
        )
        port, stop = start_server(app)
        try:
            # 同一设备配对一次：断连→重连用同一密钥，才算「网络抖动重连」
            code = db.create_mx_pairing_code()
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                device_key = json.loads(await ws.recv())["device_key"]

            async def auth_and_close():
                live = await ws_connect(port)
                await live.send(json.dumps({"op": "auth", "key": device_key}))
                assert json.loads(await live.recv()) == {"ok": True}
                await live.close()

            # 认证一条连接然后断开 → 阈值后（设备仍离线）告警一次
            await auth_and_close()
            assert await await_for(
                lambda: len(alerts) == 1
            ), "超阈值仍离线应发布告警"
            # 快速重连再断开 → 阈值去重窗内不重复告警（网络抖动不打扰）
            await auth_and_close()
            await asyncio.sleep(0.5)
            assert len(alerts) == 1, "阈值窗内重复断连不应再告警"
            # 断连事件本身每次都记录（排障依据）
            assert await await_for(
                lambda: sum(
                    1 for e in db.list_mx_ingest_events() if e["event"] == "disconnect"
                ) == 2
            ), "每次断连都应留事件记录"
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_disconnect_alert_delayed_until_threshold_elapsed():
    """断连不立即告警：阈值后才告警（仍在断开状态）；抖动秒级重连不打扰。"""
    import tempfile
    from pathlib import Path as _P

    from app.db import DB
    from app.services.mx_gateway import build_gateway_app

    async def scenario():
        tmp = _P(tempfile.mkdtemp())
        db = DB(tmp / "alert-delay.db")
        alerts = []
        app = build_gateway_app(
            db,
            on_external_post=None,
            alert_publisher=lambda title, content: alerts.append((title, content)),
            # 阈值 1.2s：断开后仍断开超过该时长才告警
            disconnect_alert_seconds=1.2,
        )
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            # 短暂断连（< 阈值即重连）：不告警——网络抖动不打扰
            await live.close()
            await asyncio.sleep(0.4)
            assert alerts == [], "阈值未到的短暂断连不应告警"
            # 阈值后仍在断开状态 → 告警（延迟检查任务到期判定）
            assert await await_for(lambda: len(alerts) == 1), \
                "超过阈值仍在断开状态应发布告警"
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_disconnect_reconnect_before_threshold_no_alert():
    """断连后阈值前重连：延迟检查发现设备已在线 → 不告警。"""

    async def scenario():
        import tempfile
        from pathlib import Path as _P

        from app.db import DB
        from app.services.mx_gateway import build_gateway_app

        tmp = _P(tempfile.mkdtemp())
        db = DB(tmp / "alert-reconnect.db")
        alerts = []
        app = build_gateway_app(
            db,
            on_external_post=None,
            alert_publisher=lambda title, content: alerts.append((title, content)),
            disconnect_alert_seconds=1.0,
        )
        port, stop = start_server(app)
        try:
            # 同一设备：配对一次，断开→阈值前重连（密钥复用）→ 保持在线
            code = db.create_mx_pairing_code()
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                device_key = json.loads(await ws.recv())["device_key"]
            live = await ws_connect(port)
            await live.send(json.dumps({"op": "auth", "key": device_key}))
            assert json.loads(await live.recv()) == {"ok": True}
            await live.close()
            # 阈值前重连并保持在线：延迟检查到期时设备已连接 → 不告警
            live = await ws_connect(port)
            await live.send(json.dumps({"op": "auth", "key": device_key}))
            assert json.loads(await live.recv()) == {"ok": True}
            await asyncio.sleep(1.6)
            assert alerts == [], "阈值前重连成功不应告警"
            await live.close()
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_disconnect_alert_immediate_when_threshold_zero():
    """阈值=0 = 立即告警口径（保留旧行为；断连即发）。"""

    async def scenario():
        import tempfile
        from pathlib import Path as _P

        from app.db import DB
        from app.services.mx_gateway import build_gateway_app

        tmp = _P(tempfile.mkdtemp())
        db = DB(tmp / "alert-zero.db")
        alerts = []
        app = build_gateway_app(
            db,
            on_external_post=None,
            alert_publisher=lambda title, content: alerts.append((title, content)),
            disconnect_alert_seconds=0,
        )
        port, stop = start_server(app)
        try:
            # 阈值 0 = 立即告警：断连后马上断（无延迟检查窗口）
            live = await pair_and_auth(port, db)
            await live.close()
            assert await await_for(lambda: len(alerts) == 1), \
                "阈值 0 应立即告警"
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_disconnect_alert_disabled_when_alerts_publisher_none():
    """未配置告警发布器（生产纯 UI 调试模式）时断连不告警（静默口径）。"""

    async def scenario():
        import tempfile
        from pathlib import Path as _P

        from app.db import DB
        from app.services.mx_gateway import build_gateway_app

        tmp = _P(tempfile.mkdtemp())
        db = DB(tmp / "alert-none.db")
        app = build_gateway_app(db, on_external_post=None, alert_publisher=None)
        port, stop = start_server(app)
        try:
            live = await pair_and_auth(port, db)
            await live.close()
            await asyncio.sleep(0.5)
            # 断连事件照常记录（排障面），只是无告警发布
            assert any(
                e["event"] == "disconnect" for e in db.list_mx_ingest_events()
            ), "断连事件应照常记录"
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


# ---- 管理面路由（S1）：配对码签发 / 设备清单 / 吊销 ----


def make_gateway_with_admin(db_path=None, admin_token="admin-test-token-123"):
    """造带管理面路由的网关 app + 共享 DB（管理面用例专用）。"""
    import tempfile
    from pathlib import Path as _P

    from app.db import DB
    from app.services.mx_gateway import build_gateway_app

    tmp = _P(tempfile.mkdtemp())
    db = DB(db_path or (tmp / "gateway-admin.db"))
    app = build_gateway_app(
        db,
        on_external_post=None,
        alert_publisher=None,
        admin_token=admin_token,
    )
    return app, db


def _admin_headers():
    return {"Authorization": "Bearer admin-test-token-123"}


def test_admin_routes_require_token():
    """管理面路由无 token / 错 token 一律 404（不暴露存在性，mx_shot 先例）。"""
    import httpx

    async def scenario():
        app, _db = make_gateway_with_admin()
        transports = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transports,
                                     base_url="http://test") as client:
            # 无 Authorization：404
            r = await client.post("/api/admin/mx-ingest/pairing-code")
            assert r.status_code == 404, r.status_code
            # 错 token：404
            r = await client.post(
                "/api/admin/mx-ingest/pairing-code",
                headers={"Authorization": "Bearer wrong"},
            )
            assert r.status_code == 404, r.status_code
            # GET devices / revoke 同口径
            r = await client.get("/api/admin/mx-ingest/devices")
            assert r.status_code == 404, r.status_code
            r = await client.post(
                "/api/admin/mx-ingest/devices/1/revoke",
                headers={"Authorization": "Bearer wrong"},
            )
            assert r.status_code == 404, r.status_code

    asyncio.run(asyncio.wait_for(scenario(), timeout=15))


def test_admin_mint_pairing_code_and_devices_list():
    """管理面签发配对码 → 扩展用它配对成功 → 设备清单可查（不含密钥哈希）。"""
    import httpx

    async def scenario():
        app, _db = make_gateway_with_admin()
        # 管理面签发配对码（带 expires_at 返回）
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/admin/mx-ingest/pairing-code", headers=_admin_headers()
            )
            assert r.status_code == 200, (r.status_code, r.text)
            body = r.json()
            code = body["code"]
            assert len(code) == 8 and code.isdigit(), body
            assert float(body["expires_at"]) > time.time(), body

        # 扩展用该码走配对（同一条真实 ws 链路）
        port, stop = start_server(app)
        try:
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                resp = json.loads(await ws.recv())
                assert resp.get("ok") is True, resp

            # 设备清单：1 台设备，未吊销
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get(
                    "/api/admin/mx-ingest/devices", headers=_admin_headers()
                )
                assert r.status_code == 200
                devices = r.json()["devices"]
                assert len(devices) == 1, devices
                assert devices[0]["revoked"] == 0
                assert "key_hash" not in devices[0], "密钥哈希不回传"
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_admin_revoke_kills_live_connection():
    """管理面吊销路由：吊销后存量连接被断（close 4003）+ 设备清单标记吊销。"""
    import httpx

    async def scenario():
        app, _db = make_gateway_with_admin()
        port, stop = start_server(app)
        try:
            # 管理面签码
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post(
                    "/api/admin/mx-ingest/pairing-code", headers=_admin_headers()
                )
                code = r.json()["code"]

            # 扩展配对 + 认证保持在线
            async with await ws_connect(port) as ws:
                await ws.send(json.dumps({"op": "pair", "code": code}))
                device_key = json.loads(await ws.recv())["device_key"]
            live = await ws_connect(port)
            await live.send(json.dumps({"op": "auth", "key": device_key}))
            assert json.loads(await live.recv()) == {"ok": True}

            # 管理面吊销该设备：存量连接即断（走路由接线，非直调 notify）
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get(
                    "/api/admin/mx-ingest/devices", headers=_admin_headers()
                )
                device_id = r.json()["devices"][0]["id"]
                r = await client.post(
                    f"/api/admin/mx-ingest/devices/{device_id}/revoke",
                    headers=_admin_headers(),
                )
                assert r.status_code == 200, r.text

            with pytest.raises(websockets.ConnectionClosed) as ei:
                await asyncio.wait_for(live.recv(), timeout=5)
            assert ei.value.rcvd.code == 4003, "吊销后必须以 close 4003 断开"

            # 设备清单显示已吊销
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get(
                    "/api/admin/mx-ingest/devices", headers=_admin_headers()
                )
                assert r.json()["devices"][0]["revoked"] == 1
        finally:
            stop()

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_full_app_has_admin_ingest_routes(tmp_path):
    """完整 create_app 组装：管理面路由随网关 router 一起挂载（组装回归）。"""
    config = Config()
    config.db_path = str(tmp_path / "full2.db")
    config.alerts_enabled = False
    app = create_app(config=config)
    paths = [getattr(r, "path", "") for r in app.router.routes]
    assert "/api/admin/mx-ingest/pairing-code" in paths
    assert "/api/admin/mx-ingest/devices" in paths
    assert "/api/admin/mx-ingest/devices/{device_id}/revoke" in paths
