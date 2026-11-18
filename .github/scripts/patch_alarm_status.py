#!/usr/bin/env python3
"""One-shot patch: report the exact-alarm status on every launch (v1.0.22)."""
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


MAIN = "android-shell/app/src/main/java/app/floatphone/shell/MainActivity.kt"

old_fn = '''    private fun promptExactAlarmOnce() {
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
    }'''

new_fn = '''    private fun reportAlarmStatus() {
        val allowed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            getSystemService(AlarmManager::class.java)?.canScheduleExactAlarms() == true
        } else {
            true
        }
        val versionName = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName
        }.getOrNull().orEmpty()

        // Always surface the real state. On some ROMs the permission is granted by
        // default (so "float" never shows up in the Alarms & reminders list) and
        // on others the list only shows apps that already asked — a toast is the
        // only way the user can tell which case they are in.
        toastOnUi("float $versionName - exact alarm: " + if (allowed) "ALLOWED" else "NOT ALLOWED")
        if (allowed) return

        runCatching {
            startActivity(
                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
                    .setData(Uri.parse("package:$packageName"))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }.onFailure {
            // A few ROMs ship no such page: fall back to the app details screen.
            toastOnUi("No Alarms & reminders page on this ROM, opening app details")
            runCatching {
                startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                        .setData(Uri.parse("package:$packageName"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
    }'''

patch(MAIN, old_fn, new_fn)
patch(MAIN, "        promptExactAlarmOnce()", "        reportAlarmStatus()")

# 1.0.21 left an uncompilable reference here: DeviceActionBridge is not an
# Activity, so "$packageName" does not resolve (must be context.packageName).
patch(
    "android-shell/app/src/main/java/app/floatphone/shell/DeviceActionBridge.kt",
    '''            "exact_alarm" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
                    .setData(Uri.parse("package:$packageName"))
            } else {
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.parse("package:$packageName"))
            }''',
    '''            "exact_alarm" -> if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
                    .setData(Uri.parse("package:${context.packageName}"))
            } else {
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.parse("package:${context.packageName}"))
            }''',
)

patch(
    "android-shell/app/build.gradle",
    '        versionCode 20\n        versionName "1.0.21"',
    "        // 1.0.22: report the exact-alarm status on every launch.\n"
    "        versionCode 21\n"
    '        versionName "1.0.22"',
)

print("OK")
