// 评论框：通过 Web3Forms 把评论发送到站长邮箱（纯静态、无后端）
//
// 使用前只需一步：
//   1. 打开 https://web3forms.com 用你想接收评论的邮箱注册
//   2. 登录后复制你的 Access Key
//   3. 替换下面这一行引号里的内容
//
// 其余代码无需改动，改完推送部署即可生效。
const WEB3FORMS_ACCESS_KEY = "4a4975cf-52fe-48fd-bb24-648fc90f2509";

(function () {
  const form = document.getElementById("comment-form");
  if (!form) return;

  const status = form.querySelector(".comment-status");
  const button = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async function (event) {
    event.preventDefault();

    if (WEB3FORMS_ACCESS_KEY === "YOUR_WEB3FORMS_ACCESS_KEY") {
      status.textContent = "站长还没配置评论功能，请稍后再来。";
      return;
    }

    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    payload.access_key = WEB3FORMS_ACCESS_KEY;
    payload.subject = "【我的浅书】收到一条新评论";
    payload.page = window.location.href;
    if (!payload.name) payload.name = "匿名访客";

    button.disabled = true;
    status.textContent = "发送中…";

    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      if (result.success) {
        status.textContent = "评论已发送，谢谢你！";
        form.reset();
      } else {
        status.textContent = "发送失败：" + (result.message || "请稍后再试。");
      }
    } catch (err) {
      status.textContent = "发送失败，请检查网络后重试。";
    } finally {
      button.disabled = false;
    }
  });
})();
