package app.floatphone.shell

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.PowerManager

/**
 * 系统闹钟到点：点亮 CPU，让网页立刻跑一次定时任务轮询，再把锁还回去。
 *
 * 网页这边只暴露一个 window.__floatDueTick（见 lib/follow-up-service.ts）。
 * 拿不到 WebView（进程被系统回收）就没法跑任务，直接结束——这种情况只能靠
 * 服务器推送兜底，不属于这里能解决的范围。
 */
class TaskAlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pendingResult = goAsync()
        val powerManager = context.getSystemService(PowerManager::class.java)
        // 只拿「唤醒 CPU」的锁，不亮屏，用户不会被无端点亮屏幕烦到。
        val wakeLock = runCatching {
            powerManager?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "float:taskAlarm")?.apply {
                setReferenceCounted(false)
                acquire(90_000L)
            }
        }.getOrNull()

        var finished = false
        fun finish() {
            if (finished) return
            finished = true
            runCatching { if (wakeLock?.isHeld == true) wakeLock.release() }
            runCatching { pendingResult.finish() }
        }

        val webView = ShellBus.webView
        if (webView == null) {
            finish()
            return
        }
        webView.post {
            runCatching {
                webView.evaluateJavascript(
                    "try{window.__floatDueTick&&window.__floatDueTick()}catch(e){}",
                    null,
                )
            }
            // 给网页留出跑完的时间（要发网络请求、生成回复、弹通知），
            // 这段时间必须持有唤醒锁，否则 CPU 一睡请求就断。
            Handler(Looper.getMainLooper()).postDelayed({ finish() }, 45_000L)
        }
    }
}
