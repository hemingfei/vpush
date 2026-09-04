# 前端 ES Modules 拆分规范

`app/static/app.js` 按区块注释拆到 `core/` 与 `views/`。行为不变。先例：`app/static/views/news.js`。

## 目录

- `app/static/core/`：跨视图共享的 UI 组件或工具（如 `html.js`、`dialog.js`）。
- `app/static/views/`：页面级视图（如 `news.js`）。一个注释区块一个文件。

不要把页面逻辑放进 `core/`，不要把通用 DOM 工具放进 `views/`。

## Factory 依赖注入

照抄 `createNewsView(dependencies)`：

```js
export function createXxxView(dependencies) {
  const { $, state, api, /* 本区块用到的其它依赖 */ } = dependencies;
  // 原区块函数与局部状态
  return { publicHandlerA, publicHandlerB };
}
```

- 只注入本区块真正用到的依赖。
- `routeRenderSeq` 用 `currentRouteSeq: () => routeRenderSeq` 注入，区块内写成 `currentRouteSeq()`（与 `news.js` 相同）。
- 区块内 `let`/`const` 状态留在 factory 闭包。若 app.js 其它函数仍要读写同一份状态，返回同一个对象引用，或在返回值上用 getter/setter，不要复制一份。
- 公开函数保持原名。内部辅助函数不必 export。

`app.js` 接线：

```js
import { createXxxView } from "./views/xxx.js";

const { publicHandlerA, publicHandlerB } = createXxxView({
  $,
  state,
  api,
  currentRouteSeq: () => routeRenderSeq,
  /* … */
});
```

把 factory 放在依赖函数都已声明之后、`INLINE_HANDLERS` 之前。

## INLINE_HANDLERS

内联 `onclick="foo()"` 仍走 `app.js` 的 `INLINE_HANDLERS` + `Object.assign(window, INLINE_HANDLERS)`。

1. 新文件用 factory 返回同名 handler。
2. `app.js` import 并解构到同名绑定。
3. `INLINE_HANDLERS` 表里对应条目继续写这个名字（不要改成 `view.foo`）。
4. 事件属性里禁止 `${fn}()`，禁止读模块词法。

谁渲染按钮，handler 就归谁。拿不准的先留在 `app.js`。

## 固定动作

每个拆分任务按这个顺序做完再提交：

1. 新建文件，factory 模式搬代码（纯位移）。
2. `app.js`：加 import → 解构公开函数 → `INLINE_HANDLERS` 继续引用同名绑定 → 删除原区块。
3. `python scripts/bump_assets.py --sync`
4. `node --input-type=module --check` 校验 `app.js` 与新文件。
5. 相关 pytest 绿。
6. 按该任务冒烟清单手工验证。
7. 独立 commit。不要和下一个拆分混在一起。

## 禁止

- 不引构建链、打包器、新测试框架。
- 不批量重命名、不顺手改逻辑、不顺手优化。
- 拆分期间不要在同一仓库并行改 `app.js`。
- 不要 `git add -A`。
