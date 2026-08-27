# MX平台接入设计方案

## 一、概述

本文档描述将MX平台接入vpush系统的技术设计方案。MX平台是一个独特的社交平台,支持通过REST API获取历史消息,通过Socket.IO WebSocket接收实时新消息。

### 核心特点更新
- **自动房间同步**: 管理后台自动显示全部MX房间，无需手动添加
- **房间即KOL**: MX房间直接映射为vpush的KOL
- **实时推送优先**: WebSocket实时消息直接推送，不走合并

## 二、项目架构

### 2.1 文件结构

```
vpush/
├── app/
│   ├── fetchers/
│   │   ├── mx/
│   │   │   ├── __init__.py
│   │   │   ├── crypto.py        # MX加密/解密模块
│   │   │   ├── client.py        # MX API客户端
│   │   │   └── ws.py            # MX Socket.IO客户端
│   │   ├── mx.py                # MX平台Fetcher主实现
│   │   └── base.py              # (已存在)Fetcher基类
│   ├── services/
│   │   └── mx_sync.py           # MX房间同步服务
│   ├── config.py                # (修改)添加MxConfig
│   ├── scheduler.py             # (修改)集成MX WebSocket
│   └── api/
│       └── admin/
│           └── mx.py            # MX管理API
├── app/static/
│   └── app.js                   # (修改)添加MX平台支持
├── config.example.yaml          # (修改)添加MX配置示例
└── requirements.txt             # (修改)添加新依赖
```

### 2.2 依赖库新增

```txt
python-socketio[asyncio-client]==5.11.0
python-lzstring==1.0.4
cryptography==44.0.1
```

## 三、概念映射

| vpush概念 | MX平台概念 | 说明 |
|---------|----------|------|
| platform | - | 固定为"mx" |
| kol_id | room.id | 房间ID |
| kol_name | room.title | 房间名称 |
| external_id | message.id | 消息ID |
| title | - | 为空或房间名称 |
| content | 从msg字段解析 | 合并所有text类型消息内容 |
| url | - | 为空或可构造房间链接 |
| published_at | message.createtime | 毫秒时间戳 |
| images | 从msg字段解析 | 提取所有pic类型的url |
| detail | 完整消息 | 原始消息JSON |

## 四、MX平台API和WebSocket格式

### 4.1 REST API格式

#### 获取房间列表 - `/api/room/list`

**请求:**
```javascript
POST /business-api/5/api/room/list
Headers:
  token: <your_token>
  Content-Type: application/json
  version: web

Body:
{
  pages: 1,
  limit: 1000000,
  tt: 1787743126875  # 当前时间戳(毫秒)
}
```

**响应(未加密):**
```json
[
  {
    "id": 16133,
    "title": "同花顺概念",
    "createtime": "2024-03-02 17:01:40",
    "msg": "[{\"type\":\"text\",\"msg\":\"消息内容\"}]",
    "msgtime": "2026-08-26 19:18:46",
    "msguid": 0,
    "avatar": "//boke.52lvin.cn/upload/1709398899689.jpg",
    "teaname": "讲师",
    "introduce": "",
    "taboo": 1,
    "color": "black",
    "textcolor": "black",
    "message_today": 421,
    "prohibition": 1,
    "webhook": "",
    "websecret": "",
    "star": 0,
    "gid": 0,
    "exttime": "2030-09-15 04:54:24"
  }
]
```

**响应(加密):**
```json
{
  "code": 200,
  "data": "<LZ-String压缩后再AES加密的密文>"
}
```
解密后:
```json
{
  "code": 200,
  "msg": "success",
  "list": [ /* 房间列表数组 */ ]
}
```

#### 获取房间消息 - `/api/msg/list`

**请求:**
```javascript
POST /business-api/5/api/msg/list
Headers:
  token: <your_token>
  Content-Type: application/json
  version: web

Body:
{
  rid: 16133,              # 房间ID
  msgid: 0,                # 消息ID游标,0=最新,其他=从该ID往前翻
  pagesize: 50,            # 每页数量
  tt: 1787743126875        # 当前时间戳(毫秒)
}
```

**响应(加密):**
```json
{
  "code": 200,
  "data": "<LZ-String压缩后再AES加密的密文>"
}
```
解密后:
```json
{
  "code": 200,
  "msg": "success",
  "list": [
    {
      "msg": "[{\"type\":\"text\",\"msg\":\"消息内容\"},{\"type\":\"pic\",\"url\":\"图片链接\"}]",
      "uid": 0,
      "rid": 16133,
      "oid": 147996512,
      "id": 148040285,
      "createtime": 1787743126875
    }
  ]
}
```

### 4.2 WebSocket格式

#### Socket.IO连接配置

```javascript
io("wss://mx.2026.naaifu.cn/msg", {
  path: "/socket.io",
  transports: ["websocket"],
  timeout: 60000,
  autoConnect: true,
  auth: {
    tt: Date.now(),           # 当前时间戳(毫秒)
    token: "<your_token>",
    version: "web"
  }
})
```

#### WebSocket事件 - `room_msg`

**接收的消息格式:**

情况A - 直接JSON:
```json
{
  "msg": "[{\"type\":\"text\",\"msg\":\"实时消息内容\"}]",
  "uid": 0,
  "rid": 16133,
  "oid": 148040286,
  "id": 148040286,
  "createtime": 1787743130000
}
```

情况B - 加密字符串:
```
"<LZ-String压缩后再AES加密的密文>"
```
解密后得到同情况A的JSON结构。

情况C - 包装对象:
```json
{
  "content": "<加密密文>",
  "other_field": "value"
}
```

### 4.3 消息内容解析 - `msg`字段

`msg`字段是一个JSON字符串,解析后格式:
```json
[
  {
    "type": "text",
    "msg": "文本内容,可包含换行符\n"
  },
  {
    "type": "pic",
    "url": "https://example.com/image.jpg"
  }
]
```

**支持的type:**
- `text`: 文本消息
- `pic`: 图片消息

### 4.4 Token过期检测

检测以下情况:
1. 响应 `code` 为 `502`
2. 响应 `code` 为 `401`
3. 响应 `msg` 包含 "token"、"登录"、"认证"、"过期"、"无效" 等关键词

## 五、加密/解密详细流程

### 5.1 密钥生成

#### API密钥

```javascript
// 对应前端 nl() 函数
function getBeijingDate() {
  const now = new Date();
  // 转换为北京时间(+8小时偏移)
  const offset = now.getTimezoneOffset() - 480;  // 480分钟=8小时
  return new Date(now.getTime() + offset * 60 * 1000 + 1440 * 60 * 1000);
}

// 对应前端 rl() 函数
function getApiKey() {
  const date = getBeijingDate();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const dateStr = `${year}-${month}-${day}`;
  
  const md5Hash = CryptoJS.MD5(dateStr).toString();
  return {
    key: md5Hash.slice(0, 16),    # 前16字节
    iv: md5Hash.slice(8, 14)      # 第8-14字节
  };
}
```

#### WebSocket密钥

```javascript
// 对应前端 wm() 函数
function getWsKey() {
  const date = new Date();  # 本地时间
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const dateStr = `${year}-${month}-${day}`;
  
  const md5Hash = CryptoJS.MD5(dateStr).toString();
  return {
    key: md5Hash.slice(0, 16),
    iv: md5Hash.slice(8, 14)
  };
}
```

### 5.2 解密流程

```
密文 → LZ-String decompress → AES-128-CBC decrypt → 明文(JSON)
```

**AES参数:**
- 模式: CBC
- 填充: PKCS7
- Key: 16字节(MD5的前16字符)
- IV: 6字节(需要补零到16字节或确认正确格式)

### 5.3 密钥降级策略

```
尝试顺序: 今天 → 昨天 → 明天 → (前天/后天?)
```

## 六、详细实现设计

### 6.1 配置模块 (`app/config.py`)

#### 新增MxConfig类

```python
@dataclass
class MxConfig:
    enabled: bool = False
    token: str = ""
    api_base: str = "https://mx.2026.naaifu.cn/business-api/5"
    ws_url: str = "wss://mx.2026.naaifu.cn/msg"
    ws_path: str = "/socket.io"
    ws_enabled: bool = True
    page_size: int = 50
    max_history_pages: int = 100
    sync_interval_hours: int = 1  # 房间同步间隔
```

#### 更新SourcesConfig

```python
@dataclass
class SourcesConfig:
    xueqiu: XueqiuConfig = field(default_factory=XueqiuConfig)
    weibo: WeiboConfig = field(default_factory=WeiboConfig)
    ima: ImaConfig = field(default_factory=ImaConfig)
    mx: MxConfig = field(default_factory=MxConfig)  # 新增
```

#### 更新环境变量映射

```python
_ENV_MAP = {
    # ... 现有配置 ...
    "MX_ENABLED": ("sources", "mx", "enabled"),
    "MX_TOKEN": ("sources", "mx", "token"),
    "MX_API_BASE": ("sources", "mx", "api_base"),
    "MX_WS_URL": ("sources", "mx", "ws_url"),
    "MX_WS_PATH": ("sources", "mx", "ws_path"),
    "MX_WS_ENABLED": ("sources", "mx", "ws_enabled"),
    "MX_PAGE_SIZE": ("sources", "mx", "page_size"),
    "MX_MAX_HISTORY_PAGES": ("sources", "mx", "max_history_pages"),
    "MX_SYNC_INTERVAL_HOURS": ("sources", "mx", "sync_interval_hours"),
}
```

### 6.2 加密/解密模块 (`app/fetchers/mx/crypto.py`)

**核心功能:**
- 北京时间日期计算(用于API密钥)
- MD5哈希生成密钥
- LZ-String解压
- AES-128-CBC解密
- 密钥降级尝试(今天/昨天/明天)

**关键函数:**
```python
def get_beijing_date(offset_days: int = 0) -> datetime:
    """获取偏移后的北京时间日期"""
    pass

def generate_key(date_str: str) -> tuple[bytes, bytes]:
    """生成AES key和IV"""
    pass

def decrypt_api_data(encrypted_data: str) -> dict | list | None:
    """解密API响应数据: LZ-String解压 + AES解密"""
    pass

def decrypt_ws_data(encrypted_data: str) -> dict | None:
    """解密WebSocket消息数据"""
    pass
```

### 6.3 MX API客户端 (`app/fetchers/mx/client.py`)

```python
class MXClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def get_rooms(self) -> list[dict]:
        """获取房间列表"""
        pass
    
    async def get_room_history(self, room_id: int, msgid: int = 0, limit: int = 50) -> list[dict]:
        """获取房间历史消息"""
        pass
```

### 6.4 Socket.IO客户端 (`app/fetchers/mx/ws.py`)

**MxWsClient类:**
```python
class MxWsClient:
    def __init__(self, config: MxConfig, on_message_callback: Callable[[dict], None]):
        self.config = config
        self.on_message = on_message_callback
        self.sio = socketio.AsyncClient()
        self._setup_handlers()
        self.connected = False
        self.last_message_at = None
    
    def _setup_handlers(self):
        @self.sio.event
        async def connect():
            logger.info("MX WebSocket connected")
            self.connected = True
        
        @self.sio.event
        async def disconnect():
            logger.info("MX WebSocket disconnected")
            self.connected = False
        
        @self.sio.event
        async def connect_error(data):
            logger.error(f"MX WebSocket connection error: {data}")
        
        @self.sio.on('room_msg')
        async def on_room_msg(data):
            await self._handle_message(data)
    
    async def connect(self):
        auth = {
            "tt": int(time.time() * 1000),
            "token": self.config.token,
            "version": "web"
        }
        await self.sio.connect(
            self.config.ws_url,
            socketio_path=self.config.ws_path,
            transports=["websocket"],
            auth=auth
        )
    
    async def disconnect(self):
        await self.sio.disconnect()
    
    async def _handle_message(self, data):
        """处理接收的消息:解密→解析→回调"""
        self.last_message_at = datetime.now()
        pass
    
    async def run_forever(self):
        """保持连接运行"""
        pass
```

### 6.5 房间同步服务 (`app/services/mx_sync.py`)

```python
import asyncio
from typing import Optional
from datetime import datetime
from app.models.kol import KOL
from app.fetchers.mx.client import MXClient
from app import logger

class MXRoomSyncService:
    def __init__(self, config: dict):
        self.config = config
        self.client = MXClient(
            base_url=config.get("api_base", "https://mx.2026.naaifu.cn/business-api/5"),
            token=config["token"]
        )
        self._last_sync: Optional[datetime] = None
    
    async def sync_rooms(self):
        """
        同步所有MX房间
        """
        logger.info("Starting MX room sync...")
        try:
            rooms = await self.client.get_rooms()
            
            for room in rooms:
                # 查找或创建KOL
                kol = await KOL.get_by_platform_id("mx", str(room["id"]))
                
                if not kol:
                    # 创建新KOL
                    kol = KOL(
                        platform="mx",
                        platform_id=str(room["id"]),
                        name=room["title"],
                        avatar=room.get("avatar", ""),
                        bio=room.get("introduce", ""),
                        extra_data={
                            "teaname": room.get("teaname"),
                            "message_today": room.get("message_today", 0),
                            "msgtime": room.get("msgtime"),
                            "createtime": room.get("createtime"),
                            "star": room.get("star", 0) == 1,
                            "enabled": True,  # 默认启用
                            "show_in_plaza": True,  # 默认显示在广场
                        }
                    )
                    await kol.save()
                    logger.info(f"Created MX KOL: {room['title']}")
                else:
                    # 更新KOL信息
                    kol.name = room["title"]
                    kol.avatar = room.get("avatar", "")
                    kol.bio = room.get("introduce", "")
                    extra = kol.extra_data or {}
                    extra.update({
                        "teaname": room.get("teaname"),
                        "message_today": room.get("message_today", 0),
                        "msgtime": room.get("msgtime"),
                        "createtime": room.get("createtime"),
                        "star": room.get("star", 0) == 1,
                    })
                    kol.extra_data = extra
                    await kol.save()
                    logger.debug(f"Updated MX KOL: {room['title']}")
            
            self._last_sync = datetime.now()
            logger.info(f"MX room sync completed, processed {len(rooms)} rooms")
        except Exception as e:
            logger.error(f"MX room sync failed: {e}")
    
    async def start_periodic_sync(self):
        """
        启动定时同步
        """
        interval = self.config.get("sync_interval_hours", 1) * 3600
        
        async def sync_loop():
            while True:
                await self.sync_rooms()
                await asyncio.sleep(interval)
        
        asyncio.create_task(sync_loop())
```

### 6.6 MX Fetcher主实现 (`app/fetchers/mx.py`)

**MxFetcher类:**
```python
class MxFetcher(Fetcher):
    platform = "mx"
    
    def __init__(self, source_config: SourcesConfig, db=None):
        self.config = source_config.mx
        self.db = db
        self.client = MXClient(self.config.api_base, self.config.token)
        self.ws_client = None
        self._room_cache = {}  # room_id -> room_info
    
    def fetch(self, kol: dict) -> list[Post]:
        """从数据库读取该房间的历史消息"""
        pass
    
    async def start_ws(self, on_message: Callable[[Post], None]):
        """启动WebSocket连接并监听实时消息"""
        pass
    
    async def stop_ws(self):
        """停止WebSocket连接"""
        pass
    
    async def fetch_room_list(self) -> list[dict]:
        """获取房间列表"""
        pass
    
    async def fetch_room_history(self, room_id: int, msgid: int = 0, limit: int = None) -> list[dict]:
        """获取房间历史消息(分页)"""
        pass
    
    async def _fetch_all_rooms_history(self):
        """拉取所有已启用房间的历史消息"""
        pass
    
    def _parse_message_to_post(self, raw_msg: dict, room_info: dict = None) -> Post | None:
        """将MX消息转换为Post对象"""
        pass
    
    def _parse_msg_content(self, msg_str: str) -> tuple[str, list[str]]:
        """解析msg字段,返回(content, images)"""
        pass
```

**更新PLATFORM_LABELS (`app/fetchers/base.py`)**
```python
PLATFORM_LABELS = {
    "xueqiu": "雪球",
    "combination": "雪球组合",
    "weibo": "微博",
    "twitter": "X",
    "ima": "ima",
    "zsxq": "知识星球",
    "mx": "MX",  # 新增
}
```

**更新PLATFORM_SHORT_LABELS (`app/fetchers/base.py`)**
```python
PLATFORM_SHORT_LABELS = {
    "xueqiu": "雪球",
    "combination": "组合",
    "weibo": "微博",
    "twitter": "X",
    "ima": "ima",
    "zsxq": "星球",
    "mx": "MX",  # 新增
}
```

### 6.7 调度器集成 (`app/scheduler.py`)

**修改点:**
1. 初始化时创建MxFetcher
2. 启动MX房间同步服务
3. 启动MX WebSocket(如果启用)
4. 实时消息处理回调(直接去重并推送,不走合并)

```python
_mx_fetcher = None
_mx_ws_task = None
_mx_sync_service = None

async def start_mx_fetcher():
    global _mx_fetcher, _mx_ws_task, _mx_sync_service
    if not config.sources.mx.enabled:
        return
    
    _mx_fetcher = MxFetcher(config.sources, db=db)
    
    # 启动房间同步服务
    _mx_sync_service = MXRoomSyncService(dict(config.sources.mx))
    await _mx_sync_service.sync_rooms()  # 立即同步一次
    await _mx_sync_service.start_periodic_sync()
    
    # 拉取历史消息
    await _mx_fetcher._fetch_all_rooms_history()
    
    # 启动WebSocket
    if config.sources.mx.ws_enabled:
        async def _on_mx_message(post: Post):
            # 直接处理实时消息,不走合并
            await _handle_new_post(_mx_fetcher, post, realtime=True)
        
        _mx_ws_task = asyncio.create_task(
            _mx_fetcher.start_ws(_on_mx_message)
        )

async def stop_mx_fetcher():
    if _mx_fetcher:
        await _mx_fetcher.stop_ws()
    if _mx_ws_task:
        _mx_ws_task.cancel()

def get_mx_ws_status():
    """获取MX WebSocket状态"""
    if _mx_fetcher and _mx_fetcher.ws_client:
        return {
            "connected": _mx_fetcher.ws_client.connected,
            "last_message_at": _mx_fetcher.ws_client.last_message_at,
        }
    return {"connected": False, "last_message_at": None}
```

### 6.8 管理API (`app/api/admin/mx.py`)

```python
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.models.kol import KOL
from app.fetchers.mx.client import MXClient
from app.services.mx_sync import MXRoomSyncService
from app.scheduler import get_mx_ws_status

router = APIRouter(prefix="/admin/sources/mx", tags=["admin", "mx"])

class MXConfigUpdate(BaseModel):
    enabled: bool
    token: str
    api_base: str = "https://mx.2026.naaifu.cn/business-api/5"
    ws_url: str = "wss://mx.2026.naaifu.cn/msg"
    ws_path: str = "/socket.io"
    ws_enabled: bool = True
    page_size: int = 50
    max_history_pages: int = 100
    sync_interval_hours: int = 1

class MXRoomUpdate(BaseModel):
    enabled: Optional[bool] = None
    show_in_plaza: Optional[bool] = None

@router.get("")
async def get_mx_config():
    """获取MX配置"""
    from app.config import config
    return {
        "enabled": config.sources.mx.enabled,
        "token": config.sources.mx.token,
        "api_base": config.sources.mx.api_base,
        "ws_url": config.sources.mx.ws_url,
        "ws_path": config.sources.mx.ws_path,
        "ws_enabled": config.sources.mx.ws_enabled,
        "page_size": config.sources.mx.page_size,
        "max_history_pages": config.sources.mx.max_history_pages,
        "sync_interval_hours": config.sources.mx.sync_interval_hours,
    }

@router.put("")
async def update_mx_config(data: MXConfigUpdate):
    """更新MX配置"""
    from app.config import update_config
    update_config("sources.mx", data.dict())
    return {"success": True}

@router.post("/test")
async def test_mx_connection(data: MXConfigUpdate):
    """测试MX连接"""
    try:
        client = MXClient(data.api_base, data.token)
        rooms = await client.get_rooms()
        return {"success": True, "room_count": len(rooms)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/rooms")
async def get_mx_rooms(search: Optional[str] = None, enabled_only: bool = False):
    """获取MX房间列表"""
    query = KOL.query.where(KOL.platform == "mx")
    
    if search:
        query = query.where(KOL.name.ilike(f"%{search}%"))
    
    kols = await query.gino.all()
    
    rooms = []
    for kol in kols:
        extra = kol.extra_data or {}
        rooms.append({
            "id": int(kol.platform_id),
            "title": kol.name,
            "avatar": kol.avatar,
            "teaname": extra.get("teaname"),
            "introduce": kol.bio,
            "message_today": extra.get("message_today", 0),
            "msgtime": extra.get("msgtime"),
            "createtime": extra.get("createtime"),
            "star": extra.get("star", False),
            "enabled": extra.get("enabled", True),
            "show_in_plaza": extra.get("show_in_plaza", True),
            "subscriber_count": kol.subscriber_count,
            "kol_id": kol.id,
        })
    
    if enabled_only:
        rooms = [r for r in rooms if r["enabled"]]
    
    return {"rooms": rooms}

@router.post("/rooms/sync")
async def sync_mx_rooms():
    """立即同步MX房间"""
    from app.config import config
    if not config.sources.mx.enabled:
        raise HTTPException(status_code=400, detail="MX not enabled")
    
    service = MXRoomSyncService(dict(config.sources.mx))
    await service.sync_rooms()
    return {"success": True}

@router.put("/rooms/{room_id}")
async def update_mx_room(room_id: int, data: MXRoomUpdate):
    """更新房间状态"""
    kol = await KOL.get_by_platform_id("mx", str(room_id))
    if not kol:
        raise HTTPException(status_code=404, detail="Room not found")
    
    extra = kol.extra_data or {}
    if data.enabled is not None:
        extra["enabled"] = data.enabled
    if data.show_in_plaza is not None:
        extra["show_in_plaza"] = data.show_in_plaza
    
    kol.extra_data = extra
    await kol.save()
    
    return {"success": True}

@router.get("/ws-status")
async def get_mx_ws_status_endpoint():
    """获取WebSocket连接状态"""
    return get_mx_ws_status()
```

### 6.9 前端集成 (`app/static/app.js`)

#### 6.9.1 平台常量更新

```javascript
const PLATFORM_LABELS = { 
    xueqiu: "雪球", 
    combination: "雪球组合", 
    weibo: "微博", 
    twitter: "X", 
    ima: "ima", 
    zsxq: "知识星球",
    mx: "MX"  // 新增
};

const PLATFORM_SHORT_LABELS = { 
    xueqiu: "雪球", 
    combination: "组合", 
    weibo: "微博", 
    twitter: "X", 
    ima: "ima", 
    zsxq: "星球",
    mx: "MX"  // 新增
};

const PLATFORM_ICONS = {
    xueqiu: "...",
    combination: "...",
    weibo: "...",
    twitter: "...",
    zsxq: "...",
    mx: "<svg class=\"pt-icon\" viewBox=\"0 0 24 24\" fill=\"currentColor\" aria-hidden=\"true\">...</svg>"  // 新增
};

const PLATFORM_TABS = ["", "xueqiu", "combination", "weibo", "twitter", "zsxq", "mx"];  // 新增mx
```

#### 6.9.2 管理后台MX页面

```javascript
async function renderAdminMX(seq) {
    const config = await api("/api/admin/sources/mx");
    const roomData = await api("/api/admin/sources/mx/rooms");
    const wsStatus = await api("/api/admin/sources/mx/ws-status");
    
    $("#main").innerHTML = `
        <div class="admin-layout">
            <div class="admin-content">
                <div class="admin-section">
                    <h2>MX平台配置</h2>
                    <div class="form-group">
                        <label>启用</label>
                        <input type="checkbox" id="mx-enabled" ${config.enabled ? "checked" : ""}>
                    </div>
                    <div class="form-group">
                        <label>API Token</label>
                        <input type="password" id="mx-token" value="${config.token}">
                    </div>
                    <div class="form-group">
                        <label>API地址</label>
                        <input type="text" id="mx-api-base" value="${config.api_base}">
                    </div>
                    <div class="form-group">
                        <label>WebSocket地址</label>
                        <input type="text" id="mx-ws-url" value="${config.ws_url}">
                    </div>
                    <div class="form-group">
                        <label>WebSocket路径</label>
                        <input type="text" id="mx-ws-path" value="${config.ws_path}">
                    </div>
                    <div class="form-group">
                        <label>同步间隔(小时)</label>
                        <input type="number" id="mx-sync-interval" value="${config.sync_interval_hours}">
                    </div>
                    <div class="form-actions">
                        <button class="btn-ghost" onclick="testMXConnection()">测试连接</button>
                        <button class="btn-normal" onclick="saveMXConfig()">保存</button>
                        <button class="btn-ghost" onclick="syncMXRooms()">立即同步房间</button>
                    </div>
                </div>
                
                <div class="admin-section">
                    <h3>WebSocket状态</h3>
                    <div class="status-badge ${wsStatus.connected ? "status-online" : "status-offline"}">
                        ${wsStatus.connected ? "已连接" : "未连接"}
                    </div>
                    ${wsStatus.last_message_at ? `<p>最后消息: ${new Date(wsStatus.last_message_at).toLocaleString()}</p>` : ""}
                </div>
                
                <div class="admin-section">
                    <div class="section-header">
                        <h3>房间列表 (${roomData.rooms.length})</h3>
                        <input type="text" placeholder="搜索房间..." oninput="filterMXRooms(this.value)" style="width:200px">
                    </div>
                    
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>房间</th>
                                    <th>讲师</th>
                                    <th>今日消息</th>
                                    <th>订阅人数</th>
                                    <th>启用</th>
                                    <th>广场显示</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="mx-rooms-tbody">
                                ${roomData.rooms.map(room => mxRoomRowHtml(room)).join("")}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function mxRoomRowHtml(room) {
    return `
        <tr data-room-id="${room.id}">
            <td>
                <div class="kol-cell">
                    <img src="${room.avatar}" class="avatar" alt="">
                    <div>
                        <div class="kol-name">${escapeHtml(room.title)}</div>
                        <div class="kol-id">MX #${room.id}</div>
                    </div>
                </div>
            </td>
            <td>${escapeHtml(room.teaname || "-")}</td>
            <td>${room.message_today}</td>
            <td>${room.subscriber_count}</td>
            <td>
                <label class="toggle-switch">
                    <input type="checkbox" ${room.enabled ? "checked" : ""} 
                           onchange="toggleMXRoomEnabled(${room.id}, this.checked)">
                    <span class="slider"></span>
                </label>
            </td>
            <td>
                <label class="toggle-switch">
                    <input type="checkbox" ${room.show_in_plaza ? "checked" : ""} 
                           onchange="toggleMXRoomPlaza(${room.id}, this.checked)">
                    <span class="slider"></span>
                </label>
            </td>
            <td>
                <button class="btn-ghost btn-sm" onclick="go('kol', ${room.kol_id})">查看</button>
            </td>
        </tr>
    `;
}

async function saveMXConfig() {
    const data = {
        enabled: $("#mx-enabled").checked,
        token: $("#mx-token").value,
        api_base: $("#mx-api-base").value,
        ws_url: $("#mx-ws-url").value,
        ws_path: $("#mx-ws-path").value,
        ws_enabled: true,
        page_size: 50,
        max_history_pages: 100,
        sync_interval_hours: parseInt($("#mx-sync-interval").value) || 1,
    };
    await api("/api/admin/sources/mx", { method: "PUT", body: JSON.stringify(data) });
    showToast("保存成功");
}

async function testMXConnection() {
    const data = {
        enabled: true,
        token: $("#mx-token").value,
        api_base: $("#mx-api-base").value,
        ws_url: $("#mx-ws-url").value,
        ws_path: $("#mx-ws-path").value,
        ws_enabled: true,
        page_size: 50,
        max_history_pages: 100,
        sync_interval_hours: 1,
    };
    const result = await api("/api/admin/sources/mx/test", { method: "POST", body: JSON.stringify(data) });
    showToast(`连接成功，发现 ${result.room_count} 个房间`);
}

async function syncMXRooms() {
    await api("/api/admin/sources/mx/rooms/sync", { method: "POST" });
    showToast("同步完成");
    renderAdminMX(routeRenderSeq);  // 刷新
}

async function toggleMXRoomEnabled(roomId, enabled) {
    await api(`/api/admin/sources/mx/rooms/${roomId}`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
    });
}

async function toggleMXRoomPlaza(roomId, showInPlaza) {
    await api(`/api/admin/sources/mx/rooms/${roomId}`, {
        method: "PUT",
        body: JSON.stringify({ show_in_plaza: showInPlaza }),
    });
}

function filterMXRooms(q) {
    q = q.toLowerCase();
    const rows = $("#mx-rooms-tbody").children;
    for (let row of rows) {
        const name = row.querySelector(".kol-name").textContent.toLowerCase();
        row.style.display = name.includes(q) ? "" : "none";
    }
}
```

#### 6.9.3 Tab切换更新

在 `switchStatsTab` 函数中添加MX tab:
```javascript
function switchStatsTab(tab) {
    state.statsTab = tab;
    if (tab === "mx") {
        renderAdminMX(routeRenderSeq);
    } else if (tab === "ima") {
        renderAdminIMA(routeRenderSeq);
    } else {
        renderAdminStatsContent();
    }
}
```

在 `renderAdminStats` 函数的tab按钮中添加:
```javascript
<button class="${state.statsTab === "mx" ? "tab-active" : ""}" onclick="switchStatsTab('mx')">
    MX
</button>
```

#### 6.9.4 广场页MX房间展示

在 `kolCard` 函数中添加MX特有的信息显示:
```javascript
function kolCard(kol) {
    // ... 现有代码 ...
    
    let extraInfo = "";
    if (kol.platform === "mx") {
        const extra = kol.extra_data || {};
        extraInfo = `
            <div class="platform-badge platform-mx">MX 实时</div>
            ${extra.teaname ? `<span class="kol-teacher">讲师: ${escapeHtml(extra.teaname)}</span>` : ""}
            ${extra.message_today ? `<span class="kol-messages-today">今日 ${extra.message_today} 条</span>` : ""}
        `;
    }
    
    // ... 现有代码 ...
}
```

#### 6.9.5 时间线MX消息展示

在 `postCard` 函数中添加MX平台标识:
```javascript
function postCard(post, options = {}) {
    // ... 现有代码 ...
    
    let platformBadge = "";
    if (post.platform === "mx") {
        platformBadge = `<span class="platform-badge platform-mx">MX 实时</span>`;
    } else if (post.platform === "wscn") {
        platformBadge = `<span class="platform-badge platform-wscn">华尔街见闻</span>`;
    }
    
    // ... 将platformBadge插入到卡片中 ...
}
```

### 6.10 配置文件示例 (`config.example.yaml`)

```yaml
sources:
  # ... 现有配置 ...
  mx:
    enabled: false
    token: ""
    api_base: "https://mx.2026.naaifu.cn/business-api/5"
    ws_url: "wss://mx.2026.naaifu.cn/msg"
    ws_path: "/socket.io"
    ws_enabled: true
    page_size: 50
    max_history_pages: 100
    sync_interval_hours: 1
```

## 七、数据格式转换

**MX消息 → Post对象:**

| Post字段 | MX来源 | 说明 |
|---------|-------|------|
| platform | - | 固定"mx" |
| kol_id | message.rid | 房间ID |
| kol_name | room.title | 房间名称(从缓存获取) |
| external_id | str(message.id) | 消息ID |
| title | - | 空字符串或房间名 |
| content | 解析message.msg | 合并所有text内容 |
| url | - | 空或构造房间链接 |
| published_at | str(message.createtime) | 毫秒时间戳字符串 |
| category | - | "" |
| post_type | - | "" |
| detail | message | 完整原始消息JSON |
| images | 解析message.msg | 提取所有pic的url |
| favorite | - | False |
| tags | - | None |
| title_src | - | "" |
| content_src | - | "" |

**MX房间 → KOL对象:**

| KOL字段 | MX来源 | 说明 |
|---------|-------|------|
| platform | - | 固定"mx" |
| platform_id | str(room.id) | 房间ID |
| name | room.title | 房间名称 |
| avatar | room.avatar | 房间头像 |
| bio | room.introduce | 房间介绍 |
| extra_data.teaname | room.teaname | 讲师名称 |
| extra_data.message_today | room.message_today | 今日消息数 |
| extra_data.msgtime | room.msgtime | 最后消息时间 |
| extra_data.createtime | room.createtime | 房间创建时间 |
| extra_data.star | room.star | 是否星标 |
| extra_data.enabled | - | 是否启用(默认true) |
| extra_data.show_in_plaza | - | 是否显示在广场(默认true) |

## 八、实现优先级

### Phase 1: 基础接入
1. 配置模块更新
2. 加密/解密模块实现
3. MX API客户端实现
4. 房间同步服务实现
5. 管理API实现
6. 管理后台基础UI
7. 前端基础集成(平台常量)

### Phase 2: 消息拉取
1. MxFetcher基础框架
2. 历史消息拉取
3. 消息格式解析
4. 集成到API
5. 广场页展示

### Phase 3: 实时推送
1. Socket.IO客户端实现
2. WebSocket消息处理
3. 调度器集成
4. 实时消息推送
5. 前端实时消息展示

### Phase 4: 优化完善
1. 房间信息缓存
2. 错误处理和重试
3. Token过期提醒
4. 监控和日志
5. 前端优化完善

## 九、关键技术注意事项

### 9.1 自动房间同步
- 系统启动时立即同步一次
- 定时同步(默认每小时)
- 支持手动触发同步
- 新房间自动创建KOL，已存在房间更新信息

### 9.2 房间状态管理
- `enabled`: 控制是否拉取和推送该房间的消息
- `show_in_plaza`: 控制是否在广场页显示该房间
- 两个状态独立，可单独设置

### 9.3 AES IV问题
需要确认正确的IV长度。如果MD5只有6字节,可能需要:
- 补零到16字节
- 或者取其他片段
- 或者分析前端代码确认

### 9.4 实时消息处理
- 直接去重并推送
- 不走合并推送机制
- 即使在免打扰时段也推送

### 9.5 数据库存储
- 复用现有的`posts`表
- 复用现有的`kol`表(存储房间信息)
- 不需要新增表

### 9.6 广场页展示
- MX房间根据`show_in_plaza`状态决定是否显示
- 显示MX特有信息(讲师、今日消息数)
- 带"MX 实时"标识
