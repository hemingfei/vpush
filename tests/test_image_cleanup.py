"""帖子本地图片清理回归测试:预览统计、按大V删除、共用图保护、孤儿清理与越权拒绝。

口径见 app/image_cleanup.py 模块注释:只删文件不改库;「老图」按帖子发布时间
(回退 fetched_at)判定;共用文件仍有范围外引用时保留;孤儿按文件 mtime 判定。
"""
import hashlib
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.db import DB
from app.image_cleanup import (
    POST_IMAGE_DIRS,
    preview_image_cleanup,
    run_image_cleanup,
)
from test_api import auth_headers, make_client, user_headers

_PREFIX_BY_FOLDER = {folder: prefix for prefix, folder in POST_IMAGE_DIRS.items()}


def _image_path(db_path, folder, remote_url, mtime=None, ext="jpg"):
    """按 avatar_cache 的 sha1 键规则造一个本地缓存图,返回磁盘路径与 posts.images URL。"""
    key = hashlib.sha1(remote_url.encode()).hexdigest()[:16]
    d = Path(db_path).parent / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{key}.{ext}"
    p.write_bytes(b"\xff\xd8" + b"fake-image-bytes" * 8)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p, f"{_PREFIX_BY_FOLDER[folder]}/{p.name}"


def _oldstamp(days=200):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _recentstamp(days=2):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _seed(db):
    """大V甲:1 张老图 + 1 张近图;大V乙:1 张老图;甲乙共用 1 张老图。"""
    ka = db.add_kol("mx", "大V甲", "mx-a")
    kb = db.add_kol("mx", "大V乙", "mx-b")
    files = {}
    files["a_old"], url = _image_path(db.path, "mx_images", "https://cdn.example/a-old.jpg")
    db.insert_post("mx", ka, "a-old", "", "甲老帖", "", _oldstamp(), images=[url])
    files["a_recent"], url = _image_path(db.path, "mx_images", "https://cdn.example/a-new.jpg")
    db.insert_post("mx", ka, "a-new", "", "甲新帖", "", _recentstamp(), images=[url])
    files["b_old"], url = _image_path(db.path, "mx_images", "https://cdn.example/b-old.jpg")
    db.insert_post("mx", kb, "b-old", "", "乙老帖", "", _oldstamp(), images=[url])
    files["shared"], url = _image_path(db.path, "mx_images", "https://cdn.example/shared.jpg")
    db.insert_post(
        "mx", kb, "b-share", "", "乙发共用图", "", _oldstamp(), images=[url]
    )
    db.insert_post("mx", ka, "a-share", "", "甲也发共用图", "", _oldstamp(), images=[url])
    return ka, kb, files


def test_parse_local_image_shape_guard():
    from app.image_cleanup import _parse_local_image

    assert _parse_local_image("/mx-images/" + "a" * 16 + ".png") == ("mx_images", "a" * 16 + ".png")
    # 远端 URL(下载失败兜底留原链)不是清理对象
    assert _parse_local_image("https://cdn.example/x.jpg") is None
    # 前缀对但文件名形态不对(穿越/子路径/非常规扩展)一律拒绝
    assert _parse_local_image("/mx-images/../../dav.db") is None
    assert _parse_local_image("/mx-images/sub/dir.jpg") is None
    assert _parse_local_image("/avatars/1.jpg") is None


def test_preview_aggregates_per_kol_and_orphans():
    tmp = tempfile.mkdtemp()
    db = DB(Path(tmp) / "t.db")
    ka, kb, _files = _seed(db)
    # 孤儿:老孤儿(该清)+ 新孤儿(未到月数,保留)+ 命名不符的杂文件(忽略)
    _image_path(db.path, "zsxq_images", "https://cdn.example/orphan-old.jpg",
                mtime=time.time() - 200 * 86400)
    _image_path(db.path, "zsxq_images", "https://cdn.example/orphan-new.jpg")
    d = Path(db.path).parent / "mx_images"
    (d / "notes.txt").write_bytes(b"junk")

    result = preview_image_cleanup(db, 3)
    by_kol = {row["kol_id"]: row for row in result["kols"]}
    assert by_kol[ka]["images"] == 2  # 甲老图 + 共用图(近图不计)
    assert by_kol[kb]["images"] == 2  # 乙老图 + 共用图
    assert by_kol[ka]["kol_name"] == "大V甲"
    assert by_kol[ka]["bytes"] > 0
    assert result["orphans"]["images"] == 1  # 只有老孤儿入选
    assert result["skipped_invalid"] == 0


def test_preview_counts_invalid_entries_and_skips_undated_posts():
    tmp = tempfile.mkdtemp()
    db = DB(Path(tmp) / "t.db")
    ka = db.add_kol("mx", "大V甲", "mx-a")
    _p, bad_img = _image_path(db.path, "mx_images", "https://cdn.example/bad.jpg")
    db.insert_post(
        "mx", ka, "bad-entry", "", "异常条目", "", _oldstamp(),
        images=[bad_img, "/mx-images/../../evil", "https://cdn.example/remote-fallback.jpg"],
    )
    pid = db.insert_post("mx", ka, "undated", "", "时间坏", "", "not-a-date", images=[bad_img])
    db._conn.execute("UPDATE posts SET fetched_at='also-bad' WHERE id=?", (pid,))
    db._conn.commit()

    result = preview_image_cleanup(db, 3)
    # 时间无法判定的帖不参与清理,其引用仍受保护
    assert result["skipped_undated"] == 1
    assert result["skipped_invalid"] == 1  # 前缀对但文件名穿越的条目
    # bad-entry 的合法老图归属甲;undated 帖引用同一文件但受保护(共用图)
    by_kol = {row["kol_id"]: row for row in result["kols"]}
    assert by_kol[ka]["images"] == 1


def test_run_deletes_selected_kol_images_and_keeps_shared():
    tmp = tempfile.mkdtemp()
    db = DB(Path(tmp) / "t.db")
    ka, kb, files = _seed(db)
    mx_dir = Path(db.path).parent / "mx_images"

    # 只清甲:共用图被乙的老帖引用(范围外),必须保留
    result = run_image_cleanup(db, 3, [ka], include_orphans=False)
    assert result["deleted_files"] == 1
    assert result["kept_shared"] == 1
    assert not files["a_old"].exists()
    assert files["shared"].exists()
    assert files["a_recent"].exists()
    assert files["b_old"].exists()

    # 甲乙都清:共用图不再有范围外引用,可以删
    assert kb > 0
    result = run_image_cleanup(db, 3, [ka, kb], include_orphans=False)
    assert result["deleted_files"] == 2  # 共用图 + 乙老图(甲老图上一轮已删,磁盘缺失不计)
    assert not files["shared"].exists()
    assert not files["b_old"].exists()


def test_run_with_orphans_and_recent_orphan_kept():
    tmp = tempfile.mkdtemp()
    db = DB(Path(tmp) / "t.db")
    ka, _kb, _files = _seed(db)
    orphan_old, _url = _image_path(
        db.path, "mx_images", "https://cdn.example/orphan-old.jpg",
        mtime=time.time() - 200 * 86400,
    )
    orphan_new, _url2 = _image_path(db.path, "mx_images", "https://cdn.example/orphan-new.jpg")

    result = run_image_cleanup(db, 3, [ka], include_orphans=True)
    assert result["orphan_files"] == 1
    assert result["orphan_bytes"] > 0
    assert not orphan_old.exists()
    assert orphan_new.exists()

    # 不带孤儿开关时孤儿一律不动
    orphan_again, _u3 = _image_path(
        db.path, "mx_images", "https://cdn.example/orphan-old2.jpg",
        mtime=time.time() - 400 * 86400,
    )
    run_image_cleanup(db, 3, [ka], include_orphans=False)
    assert orphan_again.exists()


def test_api_preview_cleanup_permissions_and_flow():
    client = make_client("imgclean.db")
    admin = auth_headers(client)
    user = user_headers(client, "plainuser1")
    db = client.app.state.db
    ka, kb, files = _seed(db)
    orphan_old, _u = _image_path(
        db.path, "mx_images", "https://cdn.example/api-orphan.jpg",
        mtime=time.time() - 200 * 86400,
    )

    assert client.post(
        "/api/admin/images/cleanup/preview", json={"months": 3}, headers=user
    ).status_code == 403

    preview = client.post(
        "/api/admin/images/cleanup/preview", json={"months": 3}, headers=admin
    )
    assert preview.status_code == 200
    data = preview.json()
    assert {row["kol_id"] for row in data["kols"]} == {ka, kb}

    empty = client.post(
        "/api/admin/images/cleanup",
        json={"months": 3, "kol_ids": [], "include_orphans": False},
        headers=admin,
    )
    assert empty.status_code == 400

    run = client.post(
        "/api/admin/images/cleanup",
        json={"months": 3, "kol_ids": [ka, kb], "include_orphans": True},
        headers=admin,
    )
    assert run.status_code == 200
    body = run.json()
    assert body["deleted_files"] == 3  # 甲老图、乙老图、共用图(两个大V都选,无范围外引用)
    assert body["orphan_files"] == 1  # 老孤儿单独计数
    assert body["freed_bytes"] > 0
    assert not files["a_old"].exists()
    assert not files["shared"].exists()
    assert not orphan_old.exists()

    assert client.post(
        "/api/admin/images/cleanup",
        json={"months": 3, "kol_ids": [ka], "include_orphans": False},
        headers=user,
    ).status_code == 403
