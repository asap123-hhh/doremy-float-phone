#!/usr/bin/env python3
"""一次性补丁：前后台通知修复（1.0.19）。幂等：已应用过的项会跳过。"""
import pathlib
import sys

ROOT = pathlib.Path(".")
KT = ROOT / "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt"
WEB = ROOT / "components/desktop-shell.tsx"
GRADLE = ROOT / "android-shell/app/build.gradle"

applied, skipped = [], []


def patch(path: pathlib.Path, marker: str, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        skipped.append(label)
        return
    if old not in text:
        raise SystemExit(f"[FAIL] 未找到锚点：{label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    applied.append(label)


ONSTOP_OLD = '''    override fun onStop() {
        super.onStop()
        CallOverlayService.onHostBackground()
        CheckInService.onHostBackground()
    }'''

ONSTOP_NEW = '''    override fun onStop() {
        super.onStop()
        CallOverlayService.onHostBackground()
        CheckInService.onHostBackground()
        // 告诉网页「已经切到后台」：网页据此判断用户是否真的在看某个会话。
        // 只靠 document.visibilityState 不够——部分 ROM 的 WebView 进后台后仍报
        // visible，后台来的新消息于是被当成「你正在看这个会话」直接吞掉：前台有横幅，
        // 切后台就只剩提示音、通知栏空空。Activity 生命周期不受 JS 影响，最可靠。
        runCatching {
            webView.evaluateJavascript(
                "try{document.documentElement.setAttribute('data-shell-bg','1')}catch(e){}",
                null,
            )
        }
    }'''

ONSTART_OLD = '''    override fun onStart() {
        super.onStart()
        CallOverlayService.onHostForeground()
        CheckInService.onHostForeground()
    }'''

ONSTART_NEW = '''    override fun onStart() {
        super.onStart()
        CallOverlayService.onHostForeground()
        CheckInService.onHostForeground()
        // 回到前台：撤掉标记，重新恢复「正在看这个会话就不打扰」的判断。
        runCatching {
            webView.evaluateJavascript(
                "try{document.documentElement.removeAttribute('data-shell-bg')}catch(e){}",
                null,
            )
        }
    }'''

WEB_OLD = '''      const isCurrentMainChat = activeApp === "chat" && activeChatSession?.id === detail.sessionId;
      const isCurrentMiniChat = showMiniChat && miniSessionRef.current?.id === detail.sessionId;'''

WEB_NEW = '''      // 「正在看这个会话就别打扰」必须同时满足「页面确实在前台可见」。
      // 壳切到后台时 WebView 的 JS 仍在跑（提示音照响），但用户根本看不到页面；
      // 旧判断只比 state，于是后台来的新消息被当成「你正在看」直接吞掉——
      // 前台有横幅和通知，切后台就只剩声音、通知栏一片空白。
      // data-shell-bg 由壳在 onStop/onStart 打上/撤销，比 visibilityState 可靠。
      const pageForeground =
        typeof document !== "undefined" &&
        document.visibilityState === "visible" &&
        !document.documentElement.hasAttribute("data-shell-bg");
      const isCurrentMainChat = pageForeground && activeApp === "chat" && activeChatSession?.id === detail.sessionId;
      const isCurrentMiniChat = pageForeground && showMiniChat && miniSessionRef.current?.id === detail.sessionId;'''

patch(KT, "data-shell-bg','1'", ONSTOP_OLD, ONSTOP_NEW, "onStop 打后台标记")
patch(KT, "removeAttribute('data-shell-bg')", ONSTART_OLD, ONSTART_NEW, "onStart 撤后台标记")
patch(WEB, "const pageForeground", WEB_OLD, WEB_NEW, "网页按前后台判断是否打扰")
patch(
    GRADLE,
    'versionName "1.0.19"',
    '        versionCode 17\n        versionName "1.0.18"',
    '        // 1.0.19：切后台也能弹——壳把前后台状态告诉网页，后台消息不再被当成「正在看」吞掉。\n'
    '        versionCode 18\n        versionName "1.0.19"',
    "版本号 1.0.19",
)

print("APPLIED:", applied or "无")
print("SKIPPED:", skipped or "无")
if not applied:
    print("nothing to commit")
    sys.exit(0)
