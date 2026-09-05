"""URL 下载安全校验：防止服务端抓取/下载时被引导访问内网地址（SSRF）。

头像缓存与飞书图片上传会下载抓取内容里携带的 URL（帖子图片、头像来自
第三方平台/RSSHub），这些地址不可信。统一经 is_safe_http_url / safe_get
校验：仅允许 http/https、拒绝环回/私网/链路本地/云元数据等保留网段，
跟随重定向时逐跳重新校验。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 3

# 直接拒绝的目标网段：环回/私网/链路本地/运营商级 NAT/云元数据/多播/保留段
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

# 嵌入 IPv4 的 IPv6 前缀（NAT64）；v4 映射用 addr.ipv4_mapped 判定，无需网段常量
_NAT64_NETWORK = ipaddress.ip_network("64:ff9b::/96")


def _blocked_ip(ip: str) -> bool:
    """单个 IP（含 IPv6 作用域后缀）是否命中拒绝网段；非法 IP 一律拒绝。"""
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return True
    # 解包嵌 IPv4 的 IPv6 字面量（::ffff:10.0.0.1 等）：不展开则对所有
    # v4 网段做 `in` 判断恒为 False，内网防护被映射写法整个绕过
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        elif addr in _NAT64_NETWORK:
            addr = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    if any(
        getattr(addr, attr)
        for attr in (
            "is_loopback",
            "is_private",
            "is_link_local",
            "is_multicast",
            "is_unspecified",
            "is_reserved",
        )
    ):
        return True
    return any(addr in net for net in _BLOCKED_NETWORKS)


def _resolve_host_ips(host: str) -> list[str]:
    """解析主机名到 IP（IPv4/IPv6 去重）；解析失败返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return list({info[4][0] for info in infos})


def is_safe_http_url(url: str) -> bool:
    """判断 URL 是否允许服务端下载：http/https 且不指向内网/保留地址。

    裸 IP 直接判定；域名解析后任一地址命中内网即拒绝（覆盖多 IP / IPv6）。
    解析失败视为不安全（宁可不下，避免 DNS 重绑定类绕过）。
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return False
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return not _blocked_ip(host)
    ips = _resolve_host_ips(host)
    if not ips:
        return False
    return not any(_blocked_ip(ip) for ip in ips)


def is_allowed_trusted_llm_base(url: str) -> bool:
    """受信 LLM：http(s) Base URL，可使用本机或内网，但拒绝 URL 凭据。"""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except ValueError:
        return False
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    return True


def is_allowed_user_llm_base(url: str) -> bool:
    """用户级 LLM：公网 http(s) Base URL，允许自定义端口；拒绝凭据和内网。"""
    raw = (url or "").strip()
    return is_allowed_trusted_llm_base(raw) and is_safe_http_url(raw)


def _pinned_request(url: str) -> tuple[str, str]:
    """返回连接到已验证 IP 的 URL 与原始 Host，消除校验后再次 DNS 解析窗口。"""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        raise ValueError(f"不安全的下载地址: {url[:80]}") from None
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise ValueError(f"不安全的下载地址: {url[:80]}")
    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = sorted(_resolve_host_ips(host))
    if not ips or any(_blocked_ip(ip) for ip in ips):
        raise ValueError(f"不安全的下载地址: {url[:80]}")
    ip = ips[0]
    ip_host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{ip_host}:{port}" if port else ip_host
    host_header = parsed.netloc.rsplit("@", 1)[-1]
    pinned = urlunparse(parsed._replace(netloc=netloc))
    return pinned, host_header


def _safe_url_label(url: str) -> str:
    """错误信息只保留 scheme/host/port/path，不泄露 query 或凭据。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid-url"
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))[:160]


def _strict_pinned_request(url: str, default_ports_only: bool) -> tuple[str, str]:
    raw = (url or "").strip()
    if len(raw) > 2048:
        raise ValueError("不安全的下载地址: URL 过长")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError:
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}") from None
    if (
        parsed.scheme not in ALLOWED_SCHEMES
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.hostname.lower() == "localhost"
    ):
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}")
    expected_port = 443 if parsed.scheme == "https" else 80
    if default_ports_only and port not in (None, expected_port):
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}")
    try:
        return _pinned_request(raw)
    except ValueError:
        raise ValueError(f"不安全的下载地址: {_safe_url_label(raw)}") from None


def _read_limited_body(response: httpx.Response, max_bytes: int) -> bytes:
    length = response.headers.get("content-length")
    if length:
        try:
            declared = int(length)
        except ValueError:
            declared = -1
        if declared > max_bytes:
            raise ValueError("响应体过大")
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ValueError("响应体过大")
    return bytes(body)


def safe_request_limited(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    default_ports_only: bool = False,
    timeout: httpx.Timeout | float = 15,
    follow_redirects: bool = True,
    content: bytes | None = None,
) -> httpx.Response:
    """固定已验证公网 IP，限制解压后的响应体；可选跟随重定向。"""
    if max_bytes < 0:
        raise ValueError("响应体大小限制无效")
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        pinned, host_header = _strict_pinned_request(current, default_ports_only)
        hostname = urlparse(current).hostname or ""
        request_headers = {**(headers or {}), "Host": host_header}
        with client.stream(
            method,
            pinned,
            timeout=timeout,
            follow_redirects=False,
            headers=request_headers,
            content=content,
            extensions={"sni_hostname": hostname},
        ) as response:
            if follow_redirects and response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    return httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        request=response.request,
                    )
                current = urljoin(current, location)
                content = None
                continue
            body = _read_limited_body(response, max_bytes)
            response_headers = dict(response.headers)
            # iter_bytes() yields decoded bytes; prevent httpx from decoding them again.
            response_headers.pop("content-encoding", None)
            response_headers.pop("content-length", None)
            return httpx.Response(
                response.status_code,
                headers=response_headers,
                content=body,
                request=response.request,
            )
    raise ValueError(f"重定向次数过多: {_safe_url_label(url)}")


def safe_get_limited(
    client: httpx.Client,
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    default_ports_only: bool = False,
    timeout: httpx.Timeout | float = 15,
) -> httpx.Response:
    """逐跳固定已验证公网 IP，并限制解压后的响应体大小。"""
    return safe_request_limited(
        client,
        "GET",
        url,
        max_bytes=max_bytes,
        headers=headers,
        default_ports_only=default_ports_only,
        timeout=timeout,
        follow_redirects=True,
    )


def safe_get(client: httpx.Client, url: str, timeout: float = 15) -> httpx.Response:
    """逐跳校验并连接到已验证 IP，保留原 Host/SNI。"""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        pinned, host_header = _pinned_request(current)
        hostname = urlparse(current).hostname or ""
        resp = client.get(
            pinned,
            timeout=timeout,
            follow_redirects=False,
            headers={"Host": host_header},
            extensions={"sni_hostname": hostname},
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                return resp
            current = urljoin(current, location)
            continue
        return resp
    raise ValueError(f"重定向次数过多: {url[:80]}")
