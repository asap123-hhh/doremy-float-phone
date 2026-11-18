package app.floatphone.shell

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * 定时任务的系统闹钟：锁屏/后台把网页叫醒。
 *
 * 为什么需要它：定时任务（追问、定时主动消息）跑在网页里，靠 Web Worker 计时。
 * 屏幕锁住或系统进入 Doze 后 WebView 会被冻结，计时器跟着停——到点不触发，
 * 等用户再打开时请求已过期（fetch failed）。这里用系统闹钟在精确时刻唤醒，
 * 唤醒后由 TaskAlarmReceiver 调网页的 window.__floatDueTick 让它立刻跑一次轮询。
 *
 * 精确闹钟在 Android 12+ 需要用户单独授予「闹钟与提醒」权限；
 * 没授权时退化成 setAndAllowWhileIdle（可能被系统推迟几分钟到几十分钟）。
 */
object TaskAlarms {
    private const val REQ_CODE = 8801
    private const val ACTION = "app.floatphone.shell.TASK_ALARM"

    private fun pendingIntent(context: Context): PendingIntent {
        val intent = Intent(context, TaskAlarmReceiver::class.java).setAction(ACTION)
        return PendingIntent.getBroadcast(
            context,
            REQ_CODE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /** 设定下一次唤醒时刻；返回 true 表示拿到了精确闹钟，false 表示只能用不精确的。 */
    fun schedule(context: Context, atMillis: Long): Boolean = runCatching {
        val manager = context.getSystemService(AlarmManager::class.java) ?: return false
        val triggerAt = atMillis.coerceAtLeast(System.currentTimeMillis() + 1_000L)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !manager.canScheduleExactAlarms()) {
            manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent(context))
            false
        } else {
            manager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent(context))
            true
        }
    }.getOrDefault(false)

    fun cancel(context: Context) {
        runCatching { context.getSystemService(AlarmManager::class.java)?.cancel(pendingIntent(context)) }
    }
}
