#!/usr/bin/env python3
"""一次性补丁：通知桥加固（1.0.18）。幂等：已应用过的项会跳过。"""
import pathlib
import sys

ROOT = pathlib.Path(".")
KT = ROOT / "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt"
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


CH_V2_BLOCK = '''        const val CH_MESSAGES = "shell_messages"
        /**
         * 降级渠道：原「角色消息」渠道被系统/用户设成 IMPORTANCE_NONE 时改发到这里。
         * Android 8+ 往被静音的渠道发通知是**静默丢弃**（不报错、通知栏什么都没有），
         * 这类情况只看代码查不出来，所以留一条能发出去的后路。
         */
        const val CH_MESSAGES_V2 = "shell_messages_v2"
    }'''

HELPERS = '''    private var webNotifId = 500

    /** 在 UI 线程弹一个提示，把「通知发不出去」的原因直接摊给用户看。 */
    private fun toastOnUi(message: String) {
        runOnUiThread {
            runCatching {
                android.widget.Toast.makeText(this@MainActivity, message, android.widget.Toast.LENGTH_SHORT).show()
            }
        }
    }

    /**
     * 选一个「真能显示出来」的角色消息渠道。
     *
     * 渠道的重要性一旦被系统或用户设成 IMPORTANCE_NONE，往里面发通知会被静默丢弃：
     * 代码不报错、通知栏什么都不出现（部分 ROM 默认就把新渠道归成静默）。
     * 这里做一次降级——发现原渠道被静音，就建一个 v2 渠道先保证通知能出来。
     */
    private fun ensureUsableMessageChannel(manager: NotificationManager): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return CH_MESSAGES
        val current = manager.getNotificationChannel(CH_MESSAGES)
        if (current == null || current.importance != NotificationManager.IMPORTANCE_NONE) {
            return CH_MESSAGES
        }
        runCatching {
            if (manager.getNotificationChannel(CH_MESSAGES_V2) == null) {
                manager.createNotificationChannel(
                    NotificationChannel(CH_MESSAGES_V2, "角色消息（新）", NotificationManager.IMPORTANCE_HIGH).apply {
                        description = "角色发来的消息"
                    },
                )
            }
        }
        return CH_MESSAGES_V2
    }

    /**
     * 首次安装后发一条纯原生自检通知。
     * 不经过网页、不依赖任何配置，专门用来确认「系统这一层」是否放行。
     */
    private fun scheduleSelfTestNotification() {
        val prefs = getSharedPreferences("shell_self_test", MODE_PRIVATE)
        if (prefs.getBoolean("notified_v2", false)) return
        android.os.Handler(mainLooper).postDelayed({
            runCatching {
                val manager = getSystemService(NotificationManager::class.java)
                if (!manager.areNotificationsEnabled()) {
                    toastOnUi("系统通知权限没开：消息只能响铃")
                    return@postDelayed
                }
                val channelId = ensureUsableMessageChannel(manager)
                val text = "看到这条，说明系统通知是通的；看不到就是被系统或渠道拦了。"
                val notification = NotificationCompat.Builder(this, channelId)
                    .setSmallIcon(R.drawable.ic_stat)
                    .setContentTitle("float 通知自检")
                    .setContentText(text)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                    .setAutoCancel(true)
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .build()
                manager.notify(999, notification)
                prefs.edit().putBoolean("notified_v2", true).apply()
            }
        }, 4000)
    }
'''

NOTIFY_HEAD_OLD = '''        fun notify(title: String, body: String, avatarUrl: String, sessionId: String?): Boolean = runCatching {
            ensureMessageChannel()
            val manager = getSystemService(NotificationManager::class.java)
            val icon = loadAvatarBitmap(avatarUrl)
            val builder = NotificationCompat.Builder(this@MainActivity, CH_MESSAGES)'''

NOTIFY_HEAD_NEW = '''        fun notify(title: String, body: String, avatarUrl: String, sessionId: String?): Boolean {
            // 头像只是锦上添花：解码/下载失败绝不能把整条通知一起吞掉（旧实现是一个
            // 大 runCatching 包住全部，头像抛异常时通知直接消失，且没有任何痕迹）。
            val icon = runCatching { loadAvatarBitmap(avatarUrl) }.getOrNull()
            return runCatching {
            ensureMessageChannel()
            val manager = getSystemService(NotificationManager::class.java)
            if (!manager.areNotificationsEnabled()) {
                toastOnUi("系统通知权限没开：消息只能响铃")
                return false
            }
            val builder = NotificationCompat.Builder(this@MainActivity, ensureUsableMessageChannel(manager))'''

NOTIFY_TAIL_OLD = '''            manager.notify(webNotifId++, builder.build())
            if (webNotifId > 900) webNotifId = 500
            true
        }.getOrDefault(false)'''

NOTIFY_TAIL_NEW = '''            manager.notify(webNotifId++, builder.build())
            if (webNotifId > 900) webNotifId = 500
            true
            }.onFailure { toastOnUi("通知发送失败：${it.message ?: it.javaClass.simpleName}") }
                .getOrDefault(false)
        }'''

patch(KT, "CH_MESSAGES_V2", '        const val CH_MESSAGES = "shell_messages"\n    }', CH_V2_BLOCK, "常量 CH_MESSAGES_V2")

patch(
    KT,
    "scheduleSelfTestNotification()",
    "        ViewCompat.requestApplyInsets(rootContainer)\n\n        webView.settings.apply {",
    "        ViewCompat.requestApplyInsets(rootContainer)\n"
    "        // 每装一次发一条原生自检通知（只在首次，之后不再打扰）：能看见说明通知通道通，\n"
    "        // 看不见就是被系统或渠道拦了——用来区分「代码问题」和「系统拦截」。\n"
    "        scheduleSelfTestNotification()\n\n        webView.settings.apply {",
    "启动自检调用",
)

patch(KT, "private fun ensureUsableMessageChannel", "    private var webNotifId = 500\n", HELPERS, "诊断与降级助手")

patch(
    KT,
    "NotificationCompat.Builder(this@MainActivity, ensureUsableMessageChannel(manager))",
    NOTIFY_HEAD_OLD,
    NOTIFY_HEAD_NEW,
    "notify 头部加固",
)

patch(
    KT,
    "toastOnUi(\"通知发送失败",
    NOTIFY_TAIL_OLD,
    NOTIFY_TAIL_NEW,
    "notify 尾部加固",
)

patch(
    GRADLE,
    'versionName "1.0.18"',
    '        versionCode 16\n        versionName "1.0.17"',
    '        // 1.0.18：通知桥加固——头像失败不再吞掉通知；渠道被静音时自动降级；首次安装发自检通知。\n'
    '        versionCode 17\n        versionName "1.0.18"',
    "版本号 1.0.18",
)

print("APPLIED:", applied or "无")
print("SKIPPED:", skipped or "无")
if not applied:
    print("nothing to commit")
    sys.exit(0)
