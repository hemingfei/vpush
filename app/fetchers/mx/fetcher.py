"""MX platform fetcher."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from urllib.parse import unquote, urlparse

from ...avatar_cache import PLATFORM_IMAGE_DIRS, cache_image_file, should_direct_access
from ..base import (
    Fetcher,
    Post,
    format_published_at,
)

logger = logging.getLogger(__name__)

# 房间信息缓存 TTL：WS 消息按 rid 找 KOL 用的缓存，过期后重查数据库，
# 避免房间改名/禁用后长期使用旧信息
ROOM_CACHE_TTL_SECONDS = 300
ROOM_CACHE_MISS_TTL_SECONDS = 60

# file 消息可能是平台把截图/图片当文件发送（如钉钉转存图），按图片处理的判定：
# URL 带图片扩展名，或 URL 完全没有扩展名（转存图常不带格式后缀，此时参考文件名
# 扩展名兜底）；URL 带其他扩展名（.pdf/.zip 等）视为真实文件，走附件保留
IMAGE_FILE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|bmp|avif)$", re.IGNORECASE)
# 任意文件扩展名（2-5 位，避免把「v1.2」这类版本号尾巴当成扩展名）
ANY_FILE_EXT_RE = re.compile(r"\.[A-Za-z0-9]{2,5}$")
# 音频扩展名：纯语音消息合成「[语音]」占位正文时区分文件类型用
AUDIO_EXT_RE = re.compile(r"\.(mp3|m4a|aac|wav|ogg|oga|opus|amr|flac)$", re.IGNORECASE)
# 纯网页宿主（公众号文章、微信/微博短链）：URL 必不带文件扩展名，会被
# 「无后缀按图片」兜底误判成图片，下载下来是 text/html，当 <img> 渲染必挂。
# 明确排除，链接卡片按附件保留
PAGE_LINK_HOSTS = {"mp.weixin.qq.com", "url.cn", "t.cn"}


def looks_like_image_url(url: str, name: str = "") -> bool:
    """判断 file 消息是否按图片处理：URL 带图片扩展名，或 URL 没有任何扩展名。"""
    parsed = urlparse(str(url or ""))
    if (parsed.hostname or "").lower() in PAGE_LINK_HOSTS:
        return False
    url_path = parsed.path
    name_path = urlparse(str(name or "")).path
    if IMAGE_FILE_EXT_RE.search(url_path):
        return True
    if ANY_FILE_EXT_RE.search(url_path):
        # URL 明确带非图片扩展名（.pdf/.zip 等）→ 真实文件
        return False
    # URL 没有后缀：文件名带扩展名时以文件名为准（如「报告.pdf」仍是文件），
    # 否则视为图片
    if ANY_FILE_EXT_RE.search(name_path):
        return bool(IMAGE_FILE_EXT_RE.search(name_path))
    return True


# text 消息内嵌文件链接的两种形态（客户端把文件分享序列化成纯文本下发，msg type
# 仍是 text 而非 file，按纯文本展示会是一行裸 URL）：
# 1. 「url=<URL>,fileName=<文件名>」键值串（URL 不含空白，可带中文或百分号编码）
# 2. 微信式分享文案「分享了一份文件：<文件名>\n<URL>」（URL 可带签名查询串）
# 仅当整条 text 就是文件分享时才提取，正文里顺带提到文件的普通消息不受影响
TEXT_FILE_KV_RE = re.compile(r"^url=(\S+),fileName=(.*)$")
TEXT_FILE_SHARE_RE = re.compile(r"^分享了一份文件[：:](.+)\n(https?://\S+)$")

# 只含列表符号的悬空占位行（「-」「- 」「*」「1.」「1、」等）。单独一个符号
# 不构成任何列表项，只会被 markdown 渲染成空圆点/孤立短横线；「---」是水平
# 分隔线不在此列（字符类限长 1）
DANGLING_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+•·◦]|\d{1,3}[.、)])\s*$")


def extract_text_embedded_file(text: str) -> dict | None:
    """整条 text 消息就是一个文件分享时提取附件 {url, name}，否则返回 None。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    url = name = ""
    kv = TEXT_FILE_KV_RE.match(raw)
    if kv:
        url, name = kv.group(1), kv.group(2).strip()
    else:
        share = TEXT_FILE_SHARE_RE.match(raw)
        if share:
            name, url = share.group(1).strip(), share.group(2)
    if not url.startswith(("http://", "https://")):
        return None
    if not name:
        # 文件名缺失时用 URL path 末段解码兜底（路径可能百分号编码）
        name = unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    return {"url": url, "name": name}


def normalize_mx_text(text: str) -> str:
    """归一化 MX 消息正文的换行：还原转义序列，折叠连续换行（不允许空行）。

    MX 服务端对正文换行做了双重转义：msg 文本 JSON 解码一次后仍会剩字面量
    「反斜杠+n/r」（与真实 CR、CRLF 混杂，如编辑前缀「xx [编辑]\r\n正文」）。
    统一还原成真实换行，再把连续换行压成单个换行；只有空白字符（含全角空格）
    的行按空行处理。

    另剔除只含列表符号的悬空占位行（如「- 」「1.」）：「文件：」后跟列表的
    帖子，文件本体是独立 file 消息、由附件卡片另行渲染，占位行留在正文里
    只会渲染成空列表项/孤立短横线。
    """
    if not text:
        return ""
    # 先处理字面量转义序列（反斜杠开头），再归并真实 CR/CRLF，顺序不能反
    s = (
        str(text)
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    # 悬空列表符号行替换为空行而非删除：大V手打的「-」「·」单字符分隔行被清掉后，
    # 上下两段正文会直接粘连；保一个空行至少段落边界还在（markdown 渲染段距同款）
    return "\n".join(
        "" if DANGLING_LIST_MARKER_RE.match(line) else line
        for line in s.split("\n")
        if line.strip() or DANGLING_LIST_MARKER_RE.match(line)
    )


class MxFetcher(Fetcher):
    platform = "mx"

    def __init__(self, source_config, db, client=None):
        super().__init__(source_config)
        self.db = db
        self.config = source_config
        # (monotonic, kol) 元组：kol 为 None 也缓存（更短 TTL），未知房间噪音事件不至于打爆数据库；
        # 采集帧解析在线程池并发执行，dict 读写靠 GIL 原子性即可（最坏情况重复查一次库）
        self._room_cache: dict = {}

    def _format_published_at(self, createtime):
        """格式化 MX 消息时间。"""
        if not createtime:
            return format_published_at(str(int(time.time())))
        try:
            if isinstance(createtime, int) or str(createtime).isdigit():
                ts = int(createtime)
                ts = ts / 1000 if ts > 1e12 else ts
                return format_published_at(str(int(ts)))
            return format_published_at(str(createtime))
        except Exception:
            return format_published_at(str(int(time.time())))

    def _parse_message_to_post(self, raw_msg, kol=None):
        """
        将 MX 消息转换为 Post 对象。
        
        Args:
            raw_msg: 原始 MX 消息
            kol: KOL 信息（如果不提供则从缓存获取）
            
        Returns:
            Post 对象或 None
        """
        try:
            # 尝试多种方式获取 room_id
            room_id = raw_msg.get("rid") or raw_msg.get("room_id")
            if not room_id:
                logger.warning(f"MX message missing room id: {raw_msg}")
                return None

            # 获取 KOL 信息
            from_room_cache = False
            if kol is None:
                kol = self._get_room_info(room_id)
                from_room_cache = kol is not None
            if not kol:
                logger.warning(f"MX room {room_id} not found")
                return None
            # 实时链路（kol 来自房间缓存）不处理管理端停用的房间，避免停用后继续
            # 白耗图片下载/解析；手动拉历史、兜底拉取显式传 kol，不受此限制（兜底
            # 已自行过滤 enabled）。缓存有 TTL，停用至多延迟一个 TTL 生效，调度器
            # 入库前还会按数据库实时状态再兜底一次
            if from_room_cache and not kol.get("enabled", True):
                logger.debug("MX room %s disabled, realtime message dropped", room_id)
                return None

            # 尝试多种方式获取 msg 字段
            msg_field = raw_msg.get("msg") or raw_msg.get("message") or ""
            content, images, files = self._parse_msg_content(msg_field)

            # 提取出的附件合入 detail["files"]（与星球口径一致）：推送渠道按此
            # 渲染 📎 附件行；原始 msg 键保留，前端时间线仍从 detail.msg 解析附件
            detail = {**raw_msg, "files": files} if files else raw_msg

            # 完全解析不出文本/图片/文件的消息才丢弃：把原始 JSON 整包当正文入库
            # 会变成垃圾推送；纯文件消息（语音/PDF 等）已在解析时合成占位正文保留
            if not content and not images and not files:
                logger.debug("MX message without parsable content dropped: %s", str(raw_msg)[:200])
                return None

            # 尝试多种方式获取消息 ID；缺 id 时生成确定性兜底键，
            # 否则所有空 id 消息共用 '' 撞 (platform, external_id) 唯一约束被静默吞掉
            msg_id = raw_msg.get("id") or raw_msg.get("msgid") or raw_msg.get("msg_id")
            if msg_id:
                external_id = str(msg_id)
            else:
                external_id = self._fallback_external_id(room_id, raw_msg, content)
                logger.warning(
                    "MX message missing id, using fallback external_id=%s room=%s",
                    external_id, room_id,
                )
            # 尝试多种方式获取创建时间
            createtime = raw_msg.get("createtime") or raw_msg.get("created_at") or raw_msg.get("ts")

            return Post(
                platform=self.platform,
                kol_id=kol["id"],
                kol_name=kol["name"],
                external_id=external_id,
                title="",
                content=content,
                url="",
                published_at=self._format_published_at(createtime),
                post_type="post",
                images=images,
                detail=detail,
            )
        except Exception:
            logger.exception("Failed to parse MX message to post")
            return None

    @staticmethod
    def _fallback_external_id(room_id, raw_msg, content):
        """缺 id 消息的确定性键：同一条消息两次到达（WS/轮询）生成同一键，去重仍有效。

        下划线开头的运行时注入字段（如 WS 层逐条补的 ``_receivedAt``）不参与
        摘要：纯图/文件消息没有正文时按原始字段序列化生成键，WS 先到、HTTP
        兜底再到的时间戳不同，若参与摘要会生成不同键绕过去重、重复入库。
        """
        createtime = raw_msg.get("createtime") or raw_msg.get("created_at") or raw_msg.get("ts")
        basis = content
        if not basis:
            stable = {k: v for k, v in raw_msg.items() if not str(k).startswith("_")}
            basis = json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.md5(basis.encode("utf-8")).hexdigest()[:12]
        if createtime:
            return f"{room_id}-{createtime}-{digest[:8]}"
        return f"{room_id}-{digest}"

    def _get_room_info(self, room_id):
        """
        获取房间信息（带 TTL 缓存，过期重查数据库）。

        Args:
            room_id: 房间 ID

        Returns:
            KOL 信息字典或 None
        """
        now = time.monotonic()
        cached = self._room_cache.get(room_id)
        if cached is not None:
            cached_at, cached_kol = cached
            ttl = ROOM_CACHE_TTL_SECONDS if cached_kol else ROOM_CACHE_MISS_TTL_SECONDS
            if now - cached_at < ttl:
                return cached_kol

        # 从数据库查询
        kol = None
        if self.db:
            kol = self.db.get_kol_by_external("mx", str(room_id))
            self._room_cache[room_id] = (now, kol)
        return kol

    def _parse_msg_content(self, msg_str):
        """
        解析 msg 字段，返回 (content, images, files)。

        Args:
            msg_str: msg 字段的 JSON 字符串

        Returns:
            (content, images, files) 元组。files 是非图片附件（语音/PDF 等）
            的 [{url, name}] 列表，原始 msg 已随 detail 入库，前端从
            detail.msg 自行解析渲染播放按钮/附件链接，这里只负责占位正文
        """
        if not msg_str:
            return "", [], []

        content_parts = []
        images = []
        files = []

        try:
            msg_list = json.loads(msg_str)
            if isinstance(msg_list, list):
                for item in msg_list:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        if item_type == "text":
                            text = item.get("msg", "")
                            if text:
                                embedded = extract_text_embedded_file(text)
                                if embedded:
                                    files.append(embedded)
                                else:
                                    content_parts.append(text)
                        elif item_type == "pic":
                            url = item.get("url", "")
                            if url:
                                self._append_image(images, url)
                        elif item_type == "file":
                            url = (item.get("url") or "").strip()
                            if url and looks_like_image_url(url, item.get("name") or ""):
                                # 返回 None 仅在 db 可用、服务端确认非图片时出现
                                if self._append_image(images, url) is None:
                                    # 「疑似图片」的 file 消息服务端返回的却是网页/文件
                                    # （content-type 非图片，如微信文章链接卡片）：
                                    # 转回附件链接保留，不进 images 当死图渲染
                                    files.append({"url": url, "name": item.get("name") or ""})
                            elif url:
                                files.append({"url": url, "name": item.get("name") or ""})
            elif isinstance(msg_list, str):
                # msg 字段是 JSON 编码的纯字符串
                content_parts.append(msg_list)
        except json.JSONDecodeError:
            # 如果不是 JSON，直接作为文本
            content_parts.append(msg_str)

        content = "\n".join(content_parts)
        # 纯文件消息（如语音）没有文字：合成占位正文保住消息不被丢弃，
        # 推送渠道和帖卡也不至于空正文
        if not content and files:
            if all(self._file_is_audio(f) for f in files):
                content = "[语音]"
            else:
                content = "[文件]"
        return normalize_mx_text(content), images[:4], files

    @staticmethod
    def _file_is_audio(file_item) -> bool:
        """按 URL path / 文件名扩展名判断附件是否音频（与前端播放按钮口径一致）。"""
        url_path = urlparse(str(file_item.get("url") or "")).path
        name = str(file_item.get("name") or "")
        return bool(AUDIO_EXT_RE.search(url_path) or AUDIO_EXT_RE.search(name))

    def _append_image(self, images, url):
        """图片统一走本地缓存，下载失败或内存库时保留原 URL。

        直连名单内的域名（如钉钉 CDN）跳过缓存，保留外链由浏览器直接访问。

        返回缓存结果；None 表示服务端确认返回非图片内容（此时不往 images 塞
        死图，调用方自行决定降级口径）。
        """
        if self.db and not should_direct_access(self.db, url):
            folder, prefix = PLATFORM_IMAGE_DIRS["mx"]
            cached = cache_image_file(self.db, url, folder, prefix)
        else:
            cached = url
        if cached is not None:
            images.append(cached)
        return cached
