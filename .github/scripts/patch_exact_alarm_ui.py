#!/usr/bin/env python3
"""One-shot patch: prompt for the exact-alarm permission on first launch (v1.0.21)."""
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
    "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt",
    "import android.content.Context",
    "import android.content.Context\nimport android.app.AlarmManager",
)

patch(
    "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt",
    "        scheduleSelfTestNotification()",
    "        scheduleSelfTestNotification()\n        promptExactAlarmOnce()",
)

patch(
    "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt",
    "    private var webNotifId = 500",
    '''    private var webNotifId = 500

    /**
     * Ask for the "Alarms & reminders" permission (Android 12+) once after install.
     *
     * This permission is what lets the shell wake the page at an exact minute for a
     * scheduled task. On several ROMs (vivo/OPPO etc.) the special-access list only
     * lists apps that have already requested it — if the shell never asks, "float"
     * does not appear there at all and the user concludes it is unsupported.
     * So we open the system grant page once; after that the user can reach it
     * from Settings like any other app.
     */
    private fun promptExactAlarmOnce() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
        val manager = getSystemService(AlarmManager::class.java) ?: return
        if (manager.canScheduleExactAlarms()) return
        val prefs = getSharedPreferences("float_shell", MODE_PRIVATE)
        if (prefs.getBoolean("exact_alarm_prompted", false)) return
        prefs.edit().putBoolean("exact_alarm_prompted", true).apply()
        toastOnUi("Please allow Alarms & reminders, otherwise scheduled tasks are delayed")
        runCatching {
            startActivity(
                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
                    .setData(Uri.parse("package:$packageName"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }''',
)

patch(
    "android-shell/app/src/main/java/app/floatphone/shell/DeviceActionBridge.kt",
    '            "battery" -> Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)',
    '            "battery" -> Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)\n'
    '            // Exact alarms for scheduled tasks ("Alarms & reminders" in Settings).\n'
    '            "exact_alarm" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {\n'
    "                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)\n"
    '                    .setData(Uri.parse("package:$packageName"))\n'
    "            } else {\n"
    "                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)\n"
    '                    .setData(Uri.parse("package:$packageName"))\n'
    "            }",
)

patch(
    "android-shell/app/build.gradle",
    '        versionCode 19\n        versionName "1.0.20"',
    "        // 1.0.21: ask for the Alarms & reminders permission on first launch.\n"
    "        versionCode 20\n"
    '        versionName "1.0.21"',
)

print("OK")
