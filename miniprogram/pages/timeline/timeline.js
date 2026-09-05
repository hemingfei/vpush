const { request, resolveAvatar } = require("../../utils/api");
const { platformLabel } = require("../../utils/labels");

Page({
  data: { posts: [], loading: true, currentTag: "" },

  onShow() {
    if (this._loadedAt && Date.now() - this._loadedAt < 30000 && this.data.posts && this.data.posts.length) {
      return;
    }
    this.load();
  },

  onPullDownRefresh() {
    this.load().finally(() => wx.stopPullDownRefresh());
  },

  async load() {
    try {
      const tagQuery = this.data.currentTag
        ? `&tag=${encodeURIComponent(this.data.currentTag)}`
        : "";
      const posts = (await request(`/api/my/feed?limit=100${tagQuery}`)).map((p) => {
        const src = (p.content_src || "").trim();
        const translated = !!(src && src !== (p.content || "").trim());
        return {
          ...p,
          platform_label: platformLabel(p.platform),
          avatar_url: resolveAvatar(p.avatar_url),
          tags: Array.isArray(p.tags) ? p.tags : [],
          translated,
          showSrc: false,
          displayTitle: p.title,
          displayContent: p.content || "（无正文）",
        };
      });
      this._loadedAt = Date.now();
      this.setData({ posts, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      wx.showToast({ title: err.message, icon: "none" });
    }
  },

  // 点击贴文标签：设置当前标签筛选并重新加载（下拉刷新保持 currentTag）
  selectTag(e) {
    const tag = e.currentTarget.dataset.tag;
    if (!tag || tag === this.data.currentTag) return;
    this.setData({ currentTag: tag, loading: true }, () => this.load());
  },

  clearTag() {
    this.setData({ currentTag: "", loading: true }, () => this.load());
  },

  goHome() {
    wx.switchTab({ url: "/pages/index/index" });
  },

  copyLink(e) {
    wx.setClipboardData({ data: e.currentTarget.dataset.url });
  },

  toggleOrigin(e) {
    const id = e.currentTarget.dataset.id;
    const posts = this.data.posts.map((p) => {
      if (p.id !== id || !p.translated) return p;
      const showSrc = !p.showSrc;
      return {
        ...p,
        showSrc,
        displayTitle: showSrc ? (p.title_src || p.title) : p.title,
        displayContent: showSrc ? (p.content_src || p.content) : (p.content || "（无正文）"),
      };
    });
    this.setData({ posts });
  },
});
