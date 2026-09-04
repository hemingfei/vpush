export function createLightbox(dependencies) {
  const { escapeHtml, imgOnError, trapFocus } = dependencies;

  // ---------- 图片灯箱（点击放大原图，背景变暗，多图可左右切换；支持滚轮/双击/双指缩放与拖拽平移） ----------
  let _lightboxImages = [];
  let _lightboxIndex = 0;
  const LB_SCALE_MAX = 5;
  let _lbScale = 1;
  let _lbTx = 0; // 图片中心相对视口中心的位移（px）
  let _lbTy = 0;
  let _lbSwipe = null; // 未放大时的滑动切图起点
  let _lbPan = null; // 放大后的单指/鼠标拖拽状态
  let _lbPinch = null; // 双指捏合的起始状态
  let _lbLastTap = 0; // 双击（双指外的原地点按两连击）检测
  let _lbLastTapX = 0;
  let _lbLastTapY = 0;
  let _lbTapFromTouchAt = 0; // 移动端双击已在 touchend 处理，用于屏蔽紧随合成的 dblclick
  let _lbOnResize = null;

  function _lbImg() {
    return document.querySelector(".lightbox-img");
  }

  // 放大后限制平移：图片比视口大的方向不允许拖出边界，小的方向保持居中
  function _lbClampPan() {
    const img = _lbImg();
    if (!img) return;
    const halfX = Math.max(0, (img.offsetWidth * _lbScale - window.innerWidth) / 2);
    const halfY = Math.max(0, (img.offsetHeight * _lbScale - window.innerHeight) / 2);
    _lbTx = Math.max(-halfX, Math.min(halfX, _lbTx));
    _lbTy = Math.max(-halfY, Math.min(halfY, _lbTy));
  }

  // 同步缩放工具条（按钮可用态、倍数文本）与图片光标；不动 transform
  function _lbSyncZoomUI() {
    const zIn = document.querySelector(".lightbox-zin");
    const zOut = document.querySelector(".lightbox-zout");
    const pct = document.querySelector(".lightbox-zpct");
    if (zIn) zIn.disabled = _lbScale >= LB_SCALE_MAX;
    if (zOut) zOut.disabled = _lbScale <= 1;
    if (pct) pct.textContent = `${Math.round(_lbScale * 100)}%`;
    const img = _lbImg();
    if (img) img.style.cursor = _lbScale > 1 ? "grab" : "";
  }

  function _lbApplyTransform(animate) {
    const img = _lbImg();
    if (!img) return;
    img.classList.toggle("lb-anim", !!animate);
    img.style.transform = `translate(${_lbTx}px, ${_lbTy}px) scale(${_lbScale})`;
    _lbSyncZoomUI();
  }

  // 以屏幕点 (x, y) 为锚缩放：锚点对应的图片内容在缩放前后保持在屏幕原位
  function _lbZoomAt(x, y, nextScale) {
    const scale = Math.min(LB_SCALE_MAX, Math.max(1, nextScale));
    if (scale === _lbScale) return;
    const k = scale / _lbScale;
    const cx = window.innerWidth / 2;
    const cy = window.innerHeight / 2;
    _lbTx = (x - cx) - k * ((x - cx) - _lbTx);
    _lbTy = (y - cy) - k * ((y - cy) - _lbTy);
    _lbScale = scale;
    _lbClampPan();
    _lbApplyTransform(false);
  }

  function _lbZoomStep(dir) {
    _lbZoomAt(window.innerWidth / 2, window.innerHeight / 2, _lbScale * (dir > 0 ? 1.4 : 1 / 1.4));
  }

  function _lbZoomReset(animate = true) {
    if (_lbScale === 1 && !_lbTx && !_lbTy) return;
    _lbScale = 1;
    _lbTx = 0;
    _lbTy = 0;
    _lbApplyTransform(animate);
  }

  function _lbDoubleTapZoom(x, y) {
    if (_lbScale > 1.05) _lbZoomReset();
    else _lbZoomAt(x, y, 2.5);
  }

  function _lbTapDetect(x, y) {
    const now = Date.now();
    if (now - _lbLastTap < 320 && Math.hypot(x - _lbLastTapX, y - _lbLastTapY) < 40) {
      _lbLastTap = 0;
      _lbTapFromTouchAt = now;
      _lbDoubleTapZoom(x, y);
      return;
    }
    _lbLastTap = now;
    _lbLastTapX = x;
    _lbLastTapY = y;
  }

  function openLightbox(img) {
    if (!img) return;
    // 收集当前帖子（同一 .post-images 容器）里的全部图片，支持左右切换
    const container = img.closest(".post-images");
    if (container) {
      _lightboxImages = [...container.querySelectorAll("img")]
        .filter((im) => !im.dataset.dead) // 已失效被隐藏的图不再进入灯箱
        .map((im) => im.currentSrc || im.src || "")
        .filter(Boolean);
    } else {
      _lightboxImages = [(img.currentSrc || img.src || "")].filter(Boolean);
    }
    if (!_lightboxImages.length) return;
    _lightboxIndex = Math.max(0, _lightboxImages.indexOf(img.currentSrc || img.src || ""));
    _lbScale = 1; _lbTx = 0; _lbTy = 0; // 上一次会话的缩放状态不带入
    _lbSwipe = _lbPan = _lbPinch = null;
    closeLightbox(); // 防重复打开
    const overlay = document.createElement("div");
    overlay.className = "lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "查看大图");
    overlay.innerHTML = `
      <button class="lightbox-close" aria-label="关闭" onclick="event.stopPropagation();closeLightbox()">✕</button>
      <div class="lightbox-zoom">
        <button class="lightbox-zbtn lightbox-zout" aria-label="缩小" onclick="event.stopPropagation();_lbZoomStep(-1)">−</button>
        <button class="lightbox-zbtn lightbox-zpct" aria-label="重置缩放" title="重置缩放" onclick="event.stopPropagation();_lbZoomReset()">100%</button>
        <button class="lightbox-zbtn lightbox-zin" aria-label="放大" onclick="event.stopPropagation();_lbZoomStep(1)">+</button>
      </div>
      <img class="lightbox-img" src="${escapeHtml(_lightboxImages[_lightboxIndex])}" alt="动态配图" draggable="false" onerror="imgOnError(this)">
      ${_lightboxImages.length > 1 ? `
        <button class="lightbox-nav lightbox-prev" aria-label="上一张" onclick="event.stopPropagation();lightboxStep(-1)">‹</button>
        <button class="lightbox-nav lightbox-next" aria-label="下一张" onclick="event.stopPropagation();lightboxStep(1)">›</button>
        <span class="lightbox-count">${_lightboxIndex + 1} / ${_lightboxImages.length}</span>` : ""}`;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeLightbox();
    });
    // 桌面双击：在倍数与 2.5x 间切换（移动端双击走 touchend，这里跳过其合成的 dblclick）
    overlay.addEventListener("dblclick", (e) => {
      if (Date.now() - _lbTapFromTouchAt < 600) return;
      if (!e.target.classList.contains("lightbox-img")) return;
      _lbDoubleTapZoom(e.clientX, e.clientY);
    });
    // 滚轮缩放，以光标为锚点
    overlay.addEventListener("wheel", (e) => {
      e.preventDefault();
      _lbZoomAt(e.clientX, e.clientY, _lbScale * (e.deltaY < 0 ? 1.18 : 1 / 1.18));
    }, { passive: false });
    // 放大后鼠标拖拽平移
    overlay.addEventListener("mousedown", (e) => {
      if (_lbScale <= 1 || !e.target.classList.contains("lightbox-img")) return;
      e.preventDefault(); // 阻止图片原生拖拽幽灵
      const img = _lbImg();
      img.classList.add("lb-dragging");
      const start = { x: e.clientX, y: e.clientY, tx: _lbTx, ty: _lbTy };
      const onMove = (ev) => {
        _lbTx = start.tx + (ev.clientX - start.x);
        _lbTy = start.ty + (ev.clientY - start.y);
        _lbClampPan();
        _lbApplyTransform(false);
      };
      const onUp = () => {
        img.classList.remove("lb-dragging");
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
    // 移动端手势：单指滑动切换图片（未放大）/ 拖拽平移（放大后），双指捏合缩放
    overlay.addEventListener("touchstart", lightboxTouchStart, { passive: true });
    overlay.addEventListener("touchmove", lightboxTouchMove, { passive: false });
    overlay.addEventListener("touchend", lightboxTouchEnd, { passive: true });
    _lbOnResize = () => {
      _lbClampPan();
      _lbApplyTransform(false);
    };
    window.addEventListener("resize", _lbOnResize);
    document.body.appendChild(overlay);
    _lbSyncZoomUI(); // 初始 1x：禁用「−」、倍数显示 100%
    document.body.classList.add("lightbox-open");
    document.addEventListener("keydown", lightboxKeyHandler);
    trapFocus(overlay, closeLightbox);
    overlay.querySelector(".lightbox-close")?.focus();
  }

  function lightboxTouchStart(e) {
    // 从箭头/关闭/缩放按钮上开始的触摸不拦截（按钮有自己的事件）
    if (e.target.closest(".lightbox-nav, .lightbox-close, .lightbox-zbtn")) return;
    if (e.touches.length >= 2) {
      // 双指捏合：记录起始指距、中点与图片状态，move 阶段据此整体换算
      const [a, b] = e.touches;
      _lbPinch = {
        dist: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY),
        x: (a.clientX + b.clientX) / 2,
        y: (a.clientY + b.clientY) / 2,
        scale: _lbScale,
        tx: _lbTx,
        ty: _lbTy,
      };
      _lbSwipe = _lbPan = null;
      return;
    }
    if (_lbScale > 1) {
      const t = e.touches[0];
      _lbPan = { x: t.clientX, y: t.clientY, tx: _lbTx, ty: _lbTy, t: Date.now() };
      return;
    }
    const t0 = e.touches[0];
    _lbSwipe = { x: t0.clientX, y: t0.clientY, t: Date.now() };
  }

  function lightboxTouchMove(e) {
    if (_lbPinch && e.touches.length >= 2) {
      e.preventDefault();
      if (_lbPinch.dist <= 0) return;
      const [a, b] = e.touches;
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      const scale = Math.min(LB_SCALE_MAX, Math.max(1, _lbPinch.scale * (dist / _lbPinch.dist)));
      const k = scale / _lbPinch.scale;
      const mx = (a.clientX + b.clientX) / 2;
      const my = (a.clientY + b.clientY) / 2;
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      // 锚点公式：起始中点对应的图片内容随两指中点移动，捏合同时完成缩放与平移
      _lbTx = (mx - cx) - k * ((_lbPinch.x - cx) - _lbPinch.tx);
      _lbTy = (my - cy) - k * ((_lbPinch.y - cy) - _lbPinch.ty);
      _lbScale = scale;
      _lbClampPan();
      _lbApplyTransform(false);
      return;
    }
    if (_lbPan && e.touches.length === 1) {
      e.preventDefault(); // 阻止松手合成 click 与页面默认手势
      const t = e.touches[0];
      _lbTx = _lbPan.tx + (t.clientX - _lbPan.x);
      _lbTy = _lbPan.ty + (t.clientY - _lbPan.y);
      _lbClampPan();
      _lbApplyTransform(false);
      return;
    }
    if (!_lbSwipe) return;
    const dx = e.touches[0].clientX - _lbSwipe.x;
    const dy = e.touches[0].clientY - _lbSwipe.y;
    // 水平滑动占优时拦截：阻止页面滚动，也阻止松手后合成 click（避免误关灯箱）
    if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) e.preventDefault();
  }

  function lightboxTouchEnd(e) {
    if (_lbPinch) {
      if (e.touches.length === 1) {
        // 抬起一根手指后无缝转为单指拖拽
        const t = e.touches[0];
        _lbPan = { x: t.clientX, y: t.clientY, tx: _lbTx, ty: _lbTy, t: Date.now() };
        _lbPinch = null;
      } else if (e.touches.length === 0) {
        _lbPinch = null;
        if (_lbScale <= 1.02) _lbZoomReset(); // 捏回 1x 附近时吸附复位
      }
      return;
    }
    if (_lbPan) {
      const t = e.changedTouches[0];
      const still = t && Date.now() - _lbPan.t < 350 && Math.hypot(t.clientX - _lbPan.x, t.clientY - _lbPan.y) < 15;
      if (e.touches.length === 0) _lbPan = null;
      if (still) _lbTapDetect(t.clientX, t.clientY); // 放大状态下的原地点按：参与双击检测（双击复位）
      return;
    }
    if (!_lbSwipe) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - _lbSwipe.x;
    const dy = t.clientY - _lbSwipe.y;
    _lbSwipe = null;
    if (Math.hypot(dx, dy) < 24) {
      _lbTapDetect(t.clientX, t.clientY); // 原地点按：双击检测（双击放大 2.5x）
      return;
    }
    // 阈值：水平 40px 且明显占优；放大后的拖拽平移在 _lbPan 分支处理，不走切图
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    lightboxStep(dx < 0 ? 1 : -1);
  }

  function lightboxStep(dir) {
    if (_lightboxImages.length < 2) return;
    _lightboxIndex = (_lightboxIndex + dir + _lightboxImages.length) % _lightboxImages.length;
    const img = document.querySelector(".lightbox-img");
    if (!img) return;
    _lbZoomReset(false); // 换图复位缩放
    img.style.opacity = "0";
    setTimeout(() => {
      img.src = _lightboxImages[_lightboxIndex];
      img.style.opacity = "";
      img.style.display = ""; // 上一张若已失效被隐藏，切图时恢复
      img.onerror = () => imgOnError(img);
      document.querySelector(".lightbox-dead")?.remove();
      const count = document.querySelector(".lightbox-count");
      if (count) count.textContent = `${_lightboxIndex + 1} / ${_lightboxImages.length}`;
    }, 120); // 与淡出过渡衔接
  }

  function lightboxKeyHandler(e) {
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") lightboxStep(-1);
    else if (e.key === "ArrowRight") lightboxStep(1);
    else if (e.key === "+" || e.key === "=") _lbZoomStep(1);
    else if (e.key === "-" || e.key === "_") _lbZoomStep(-1);
    else if (e.key === "0") _lbZoomReset();
  }

  function closeLightbox() {
    const overlay = document.querySelector(".lightbox:not(.closing)");
    if (!overlay) return;
    _lbSwipe = _lbPan = _lbPinch = null;
    if (_lbOnResize) {
      window.removeEventListener("resize", _lbOnResize);
      _lbOnResize = null;
    }
    overlay.classList.add("closing"); // 触发淡出+轻微缩小动画
    // 动画结束后移除 DOM；reduced-motion 下 animation 被禁用（animationend 不触发），用超时兜底
    const remove = () => overlay.remove();
    overlay.addEventListener("animationend", remove, { once: true });
    setTimeout(remove, 240); // 略大于关闭动画 200ms；reduced-motion 下 animationend 不触发时兜底
    document.body.classList.remove("lightbox-open");
    document.removeEventListener("keydown", lightboxKeyHandler);
  }

  return { openLightbox, closeLightbox, lightboxStep, _lbZoomStep, _lbZoomReset };
}
