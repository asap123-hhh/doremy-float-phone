"""一次性补丁：安卓壳直连自有站点 + 页面铺满真机屏幕。

在 GitHub Actions runner 里执行（见 .github/workflows/shell-native-fixes.yml），
跑完后由工作流自己删除本文件。全部改动都是幂等的：重复执行只会打印 already applied。
"""

import pathlib
import re

MAIN = pathlib.Path("android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt")
GRADLE = pathlib.Path("android-shell/app/build.gradle")
CSS = pathlib.Path("styles/phone-shell.css")

done = []

# ── 1. MainActivity ─────────────────────────────────────────────────────────
src = MAIN.read_text(encoding="utf-8")

# 1a. 移除把 SITE_URL 改写到第三方镜像的代理
START = "        val proxyClient = OkHttpClient.Builder().followRedirects(true).build()"
END = "            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {"
if START in src:
    i = src.index(START)
    j = src.index(END, i)
    comment = (
        "        // 这里曾有一段把发往 SITE_URL 的请求全部改写到第三方镜像\n"
        "        // （float.wenyuchu0216.cc.cd）的 shouldInterceptRequest 代理，整段移除：\n"
        "        //   1. 壳加载的不是本仓库部署的站点，改代码 / 重新部署在 App 里永远看不到；\n"
        "        //   2. 所有 /api 请求（聊天、角色卡、密钥）都会经过那台第三方服务器。\n"
        "        // 壳必须直连编译时写入的 SITE_URL。\n"
    )
    src = src[:i] + comment + "        webView.webViewClient = object : WebViewClient() {\n" + src[j:]
    done.append("移除第三方镜像代理")

# 1b. 开启 viewport，让 WebView 按网页 viewport 排版
if "useWideViewPort" not in src:
    old = '            userAgentString = "$userAgentString FloatShell/$VERSION"\n        }'
    new = (
        '            userAgentString = "$userAgentString FloatShell/$VERSION"\n'
        '            // 尊重网页的 viewport meta：否则 WebView 把页面当 980px 桌面页整体缩小，\n'
        '            // CSS 里 @media (max-width:500px) 的整屏分支永远不命中，\n'
        '            // 最终画出 390px 的「虚拟手机壳」，在真机上就是手机套手机。\n'
        '            useWideViewPort = true\n'
        '            loadWithOverviewMode = true\n'
        '            // App 不是可缩放的网页，关掉双指缩放与缩放按钮。\n'
        '            builtInZoomControls = false\n'
        '            displayZoomControls = false\n'
        '            setSupportZoom(false)\n'
        '        }'
    )
    assert old in src, "settings anchor not found"
    src = src.replace(old, new, 1)
    done.append("开启 useWideViewPort")

# 1c. 整屏样式注入常量
JS = '''        /**
         * 壳内强制「整屏铺满、去掉虚拟机身」的样式。
         *
         * 网页那套整屏规则只写在 @media (max-width:500px) and (hover:none) and (pointer:coarse)
         * 里，而 WebView 对 hover / pointer 的求值随版本和机型变化，这条查询并不稳定命中；
         * 一旦不命中就走桌面分支，390px 的虚拟手机壳连同金属边框、侧键一起被按真机像素
         * 放大，表现为机身溢出屏幕右侧。
         *
         * App 里页面本来就该占满整块屏幕，所以这里在每次加载后注入一份等价样式，
         * 不依赖媒体查询，也不要求站点已经重新部署。
         */
        const val SHELL_FULLSCREEN_JS = """(function(){var d=document;var r=d.documentElement;r.setAttribute('data-float-shell','1');if(d.getElementById('float-shell-native'))return;var s=d.createElement('style');s.id='float-shell-native';s.textContent=[
'html[data-float-shell="1"]{--phone-screen-width:100vw;--phone-screen-height:100lvh;--phone-screen-radius:0px;--phone-frame-size:0px;--phone-case-padding:0px;--phone-case-border-size:0px;--phone-frame-radius:0px;--phone-case-radius:0px;--status-bar-drop:0px}',
'html[data-float-shell="1"] body{overflow:hidden;width:100vw;height:100lvh;background:var(--c-page-body-bg)}',
'html[data-float-shell="1"] .app-root,html[data-float-shell="1"] .app-root.splash-root{width:100vw;height:100lvh;margin:0;padding:0;display:flex;align-items:flex-start;justify-content:flex-start;overflow:hidden}',
'html[data-float-shell="1"] .phone-shell-wrap,html[data-float-shell="1"] .splash-shell-wrap{width:100vw;margin:0;gap:0;transform:none}',
'html[data-float-shell="1"] .phone-shell-wrap .phone-case{width:100vw;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}',
'html[data-float-shell="1"] .phone-shell-wrap .phone-case::before,html[data-float-shell="1"] .phone-shell-wrap .phone-case::after{display:none}',
'html[data-float-shell="1"] .phone-shell-wrap .phone-frame{width:100vw;padding:0;border-radius:0;background:transparent;box-shadow:none}',
'html[data-float-shell="1"] .phone-shell-wrap .phone-frame::before,html[data-float-shell="1"] .phone-shell-wrap .phone-frame::after{display:none}',
'html[data-float-shell="1"] .phone-shell{width:100vw;height:100lvh;border-radius:0}'
].join('');d.head.appendChild(s);})();"""'''

if "SHELL_FULLSCREEN_JS" not in src:
    anchor = '        const val VERSION = "1.0.10"'
    assert anchor in src, "VERSION anchor not found"
    src = src.replace(anchor, anchor + "\n\n" + JS, 1)
    done.append("整屏注入常量")

# 1d. 页面加载完成后注入
if "onPageFinished" not in src:
    fin_anchor = (
        "                return runCatching {\n"
        "                    startActivity(Intent(Intent.ACTION_VIEW, url)); true\n"
        "                }.getOrDefault(true)\n"
        "            }\n"
        "        }"
    )
    fin_new = (
        "                return runCatching {\n"
        "                    startActivity(Intent(Intent.ACTION_VIEW, url)); true\n"
        "                }.getOrDefault(true)\n"
        "            }\n"
        "\n"
        "            override fun onPageFinished(view: WebView, url: String) {\n"
        "                super.onPageFinished(view, url)\n"
        "                // 每次页面加载完成后注入整屏样式；SPA 内部跳转不会丢（属性挂在 html 上），\n"
        "                // 重复注入按 id 判重直接返回。\n"
        "                view.evaluateJavascript(SHELL_FULLSCREEN_JS, null)\n"
        "            }\n"
        "        }"
    )
    assert fin_anchor in src, "onPageFinished anchor not found"
    src = src.replace(fin_anchor, fin_new, 1)
    done.append("onPageFinished 注入")

MAIN.write_text(src, encoding="utf-8")

# ── 2. build.gradle：版本号（保证覆盖安装） ─────────────────────────────────
g = GRADLE.read_text(encoding="utf-8")
g2 = re.sub(r"versionCode \d+", "versionCode 15", g)
g2 = re.sub(r'versionName "[^"]*"', 'versionName "1.0.16"', g2)
if g2 != g:
    GRADLE.write_text(g2, encoding="utf-8")
    done.append("版本号 15 / 1.0.16")

# ── 3. styles/phone-shell.css：网页侧整屏规则 ───────────────────────────────
CSS_BLOCK = """/* ════════════════════════════════════════════════════════════════════
   FloatShell（安卓壳 / APK）内：页面就是真机本身，不再画虚拟手机
   ────────────────────────────────────────────────────────────────────
   App 里 WebView 是全屏加载本站的，不该再出现一台 390×844 的「手机套手机」。

   整屏规则原本只写在 @media (max-width:500px) and (hover:none) and (pointer:coarse)
   里，但 WebView 对 hover / pointer 的求值随版本和机型变化，这条查询并不稳定命中；
   一旦不命中就走桌面分支，390px 的手机壳连同金属边框、侧键一起被按真机像素放大，
   表现为机身溢出屏幕右侧。

   所以改用确定性的钩子：壳在每次页面加载后给 <html> 打上 data-float-shell="1"，
   CSS 只认这个属性，完全不依赖媒体查询。普通浏览器没有这个属性，表现保持原样。
   ════════════════════════════════════════════════════════════════════ */

html[data-float-shell="1"] {
  --phone-screen-width: 100vw;
  --phone-screen-height: 100lvh;
  --phone-screen-radius: 0px;
  --phone-frame-size: 0px;
  --phone-frame-radius: 0px;
  --phone-case-padding: 0px;
  --phone-case-border-size: 0px;
  --phone-case-radius: 0px;
  --status-bar-drop: 0px;
}

html[data-float-shell="1"] body {
  overflow: hidden;
  width: 100vw;
  height: 100lvh;
  background: var(--c-page-body-bg);
}

html[data-float-shell="1"] .app-root,
html[data-float-shell="1"] .app-root.splash-root {
  width: 100vw;
  height: 100lvh;
  margin: 0;
  padding: 0;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  overflow: hidden;
}

html[data-float-shell="1"] .phone-shell-wrap,
html[data-float-shell="1"] .splash-shell-wrap {
  width: 100vw;
  margin: 0;
  gap: 0;
  transform: none;
}

/* 外层金属中框：透明化，连侧键伪元素一起关掉 */
html[data-float-shell="1"] .phone-shell-wrap .phone-case,
html[data-float-shell="1"] .splash-shell-wrap .phone-case {
  width: 100vw;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

html[data-float-shell="1"] .phone-shell-wrap .phone-case::before,
html[data-float-shell="1"] .phone-shell-wrap .phone-case::after,
html[data-float-shell="1"] .splash-shell-wrap .phone-case::before,
html[data-float-shell="1"] .splash-shell-wrap .phone-case::after {
  display: none;
}

/* 内层黑色边框 */
html[data-float-shell="1"] .phone-shell-wrap .phone-frame,
html[data-float-shell="1"] .splash-shell-wrap .phone-frame {
  width: 100vw;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

html[data-float-shell="1"] .phone-shell-wrap .phone-frame::before,
html[data-float-shell="1"] .phone-shell-wrap .phone-frame::after,
html[data-float-shell="1"] .splash-shell-wrap .phone-frame::before,
html[data-float-shell="1"] .splash-shell-wrap .phone-frame::after {
  display: none;
}

/* 屏幕本体：铺满，圆角归零（真机圆角由设备决定，网页再画一层只会多出一圈） */
html[data-float-shell="1"] .phone-shell {
  width: 100vw;
  height: 100lvh;
  border-radius: 0;
}
"""

css = CSS.read_text(encoding="utf-8")
if 'html[data-float-shell="1"]' not in css:
    CSS.write_text(css.rstrip() + "\n\n" + CSS_BLOCK, encoding="utf-8")
    done.append("styles/phone-shell.css 整屏规则")

print("APPLIED:", ",".join(done) if done else "already applied")
