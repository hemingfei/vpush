/**
 * 模态框无障碍焦点管理 (A11y / Focus Trap)：
 * 1. 捕获 Tab / Shift+Tab 循环；
 * 2. 响应 Escape 关闭；
 * 3. 弹窗销毁时自动还原焦点至触发元素。
 */
export function trapFocus(container, onEscape) {
  const previousActive = document.activeElement;
  const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (typeof onEscape === "function") {
        e.preventDefault();
        onEscape();
      }
      return;
    }
    if (e.key !== "Tab") return;
    const focusables = Array.from(container.querySelectorAll(focusableSelector)).filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (!focusables.length) {
      e.preventDefault();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey) {
      if (document.activeElement === first || !container.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last || !container.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  container.addEventListener("keydown", handleKeydown);

  setTimeout(() => {
    if (!container.contains(document.activeElement)) {
      const initial = container.querySelector("[autofocus]") || container.querySelector(focusableSelector);
      if (initial) initial.focus();
    }
  }, 0);

  const observer = new MutationObserver(() => {
    if (!document.body.contains(container)) {
      observer.disconnect();
      container.removeEventListener("keydown", handleKeydown);
      if (previousActive && previousActive.isConnected) {
        previousActive.focus();
      }
    }
  });
  observer.observe(document.body, { childList: true });

  return () => {
    observer.disconnect();
    container.removeEventListener("keydown", handleKeydown);
    if (previousActive && previousActive.isConnected) {
      previousActive.focus();
    }
  };
}

/**
 * Body 滚动锁（弹窗打开期间禁止背景页面滚动，防止弹窗内滚动穿透到下面的列表）：
 * 用 position:fixed 锁定 body 而非 overflow:hidden —— 后者在带 sticky 元素的页面上
 * 可能让浏览器把 scrollY 归零并发出合成 scroll 事件，触发其他页面的滚动监听
 * （如最新动态的 tlSyncScrollChrome → refreshTimeline → scrollTo(0)）；
 * position:fixed 不产生 scroll 事件，全部解锁后恢复 inline 样式 + scrollTo 即可。
 * 引用计数：弹窗可叠加（新闻弹窗上再开确认框等），全部关闭才恢复滚动位置。
 */
let _lockCount = 0;
let _savedScrollY = 0;

export function lockBodyScroll() {
  if (_lockCount === 0) {
    _savedScrollY = window.scrollY;
    document.body.style.position = "fixed";
    document.body.style.top = `-${_savedScrollY}px`;
    document.body.style.left = "0";
    document.body.style.right = "0";
    document.body.style.width = "100%";
    document.body.style.overflow = "hidden";
  }
  _lockCount += 1;
}

export function unlockBodyScroll() {
  if (_lockCount === 0) return; // 无锁可解（如路由切换清理时弹窗早已关闭）
  _lockCount -= 1;
  if (_lockCount === 0) {
    document.body.style.position = "";
    document.body.style.top = "";
    document.body.style.left = "";
    document.body.style.right = "";
    document.body.style.width = "";
    document.body.style.overflow = "";
    window.scrollTo(0, _savedScrollY);
  }
}
