#!/usr/bin/env python3
"""One-shot patch: native exact alarms for scheduled tasks (v1.0.20)."""
import pathlib
import sys


def patch(rel, old, new):
    path = pathlib.Path(rel)
    text = path.read_text()
    if old not in text:
        print("MISS", rel)
        sys.exit(1)
    path.write_text(text.replace(old, new, 1))
    print("PATCH", rel)


patch(
    "lib/chat-storage.ts",
    'import { kvGet, kvSet, registerKvMigration } from "./kv-db";',
    'import { kvGet, kvSet, registerKvMigration } from "./kv-db";\n'
    'import { reportShellAlarms } from "./shell-alarm-bridge";',
)

patch(
    "lib/chat-storage.ts",
    '''function saveAllFollowUpSchedules(schedules: FollowUpSchedule[]): void {
    if (typeof window === "undefined") return;
    kvSet(FOLLOW_UP_SCHEDULES_KEY, JSON.stringify(schedules));
}''',
    '''function saveAllFollowUpSchedules(schedules: FollowUpSchedule[]): void {
    if (typeof window === "undefined") return;
    kvSet(FOLLOW_UP_SCHEDULES_KEY, JSON.stringify(schedules));
    // Hand the next trigger time to the Android shell: when the screen is locked
    // the web timers are frozen, only a system alarm can wake the WebView.
    reportShellAlarms(
        "followup",
        schedules.map(item => ({ id: item.sessionId, at: item.fireAt })),
    );
}''',
)

patch(
    "lib/timed-wake-storage.ts",
    'import { kvGet, kvSet, registerKvMigration } from "./kv-db";',
    'import { kvGet, kvSet, registerKvMigration } from "./kv-db";\n'
    'import { reportShellAlarms } from "./shell-alarm-bridge";',
)

patch(
    "lib/timed-wake-storage.ts",
    "    markBailoutDirty();\n}",
    "    markBailoutDirty();\n"
    "    // Same as follow-ups: let the shell arm a system alarm for this wake-up.\n"
    "    reportShellAlarms(\n"
    '        "timedwake",\n'
    "        schedules.map(item => ({ id: item.id, at: item.fireAt })),\n"
    "    );\n"
    "}",
)

patch(
    "lib/follow-up-service.ts",
    "    stopInterval = bgSetInterval(pollSchedules, POLL_INTERVAL_MS);",
    "    stopInterval = bgSetInterval(pollSchedules, POLL_INTERVAL_MS);\n"
    '    if (typeof window !== "undefined") {\n'
    "        // The shell's system alarm calls this on wake-up: poll immediately\n"
    "        // instead of waiting for the next interval (timers are frozen when locked).\n"
    "        (window as unknown as { __floatDueTick?: () => void }).__floatDueTick = () => pollSchedules();\n"
    "    }",
)

patch(
    "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt",
    "import android.media.AudioManager",
    "import android.media.AudioManager\nimport org.json.JSONArray",
)

patch(
    "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt",
    "        fun isTorchOn(): Boolean = deviceAction.isTorchOn()",
    '''        fun isTorchOn(): Boolean = deviceAction.isTorchOn()

        // Scheduled tasks: the page reports pending trigger times as [{id,at}]
        // (at = epoch millis). The shell arms one exact alarm for the earliest.
        // Returns true when the exact-alarm permission is available.
        @JavascriptInterface
        fun setTaskAlarms(json: String): Boolean = runCatching {
            val items = JSONArray(json)
            var earliest = Long.MAX_VALUE
            for (i in 0 until items.length()) {
                val at = items.optJSONObject(i)?.optLong("at", 0L) ?: 0L
                if (at > 0L && at < earliest) earliest = at
            }
            if (earliest == Long.MAX_VALUE) {
                TaskAlarms.cancel(this@MainActivity)
                true
            } else {
                TaskAlarms.schedule(this@MainActivity, earliest)
            }
        }.getOrDefault(false)''',
)

patch(
    "android-shell/app/src/main/AndroidManifest.xml",
    '    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />',
    '    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />\n'
    "    <!-- Exact alarms for scheduled tasks: wake the WebView on time while the\n"
    "         screen is locked. Android 12+ needs the user to grant Alarms & reminders. -->\n"
    '    <uses-permission android:name="android.permission.SCHEDULE_EXACT_ALARM" />\n'
    '    <uses-permission android:name="android.permission.WAKE_LOCK" />',
)

patch(
    "android-shell/app/src/main/AndroidManifest.xml",
    '''        <receiver
            android:name=".BootReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>''',
    '''        <receiver
            android:name=".BootReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>

        <!-- Fires when a scheduled task is due; wakes the page without lighting the screen. -->
        <receiver
            android:name=".TaskAlarmReceiver"
            android:exported="false" />''',
)

patch(
    "android-shell/app/build.gradle",
    '        versionCode 18\n        versionName "1.0.19"',
    "        // 1.0.20: scheduled tasks are driven by a system exact alarm.\n"
    "        versionCode 19\n"
    '        versionName "1.0.20"',
)

print("OK")
