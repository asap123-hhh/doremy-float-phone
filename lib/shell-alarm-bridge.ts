// lib/shell-alarm-bridge.ts
//
// 把「下一次要触发的时刻」交给安卓壳，让壳用系统精确闹钟在锁屏/后台把网页叫醒。
//
// 为什么需要它：定时任务（追问、定时主动消息…）都跑在网页里，靠 Web Worker 计时。
// 屏幕锁住、系统进入省电（Doze）后，WebView 会被冻结，计时器一起停——到点不触发；
// 等用户再打开时请求早已过期，表现为「锁屏收不到通知 + fetch failed」。
// 壳拿到时刻后会用 AlarmManager 精确唤醒网页，网页只需暴露一个
// window.__floatDueTick（见 lib/follow-up-service.ts 的注册处）。
//
// 这里刻意不 import 任何存储模块：调用方（chat-storage / timed-wake-storage）
// 各自把自己那份待触发列表报上来，避免 storage ↔ bridge 的循环依赖。

type AlarmBridge = { setTaskAlarms?: (json: string) => boolean };

type AlarmItem = { id: string; at: number };

const buckets: Record<string, AlarmItem[]> = {};
/** 只把最近要触发的几条交给壳，避免闹钟队列被长尾任务占满。 */
const MAX_ALARMS = 8;

function getBridge(): AlarmBridge | null {
    if (typeof window === "undefined") return null;
    const candidate = (window as unknown as { AndroidShell?: AlarmBridge }).AndroidShell;
    return candidate && typeof candidate.setTaskAlarms === "function" ? candidate : null;
}

function flush(): void {
    const bridge = getBridge();
    if (!bridge) return;
    const now = Date.now();
    const items = Object.values(buckets)
        .flat()
        .filter(item => Number.isFinite(item.at) && item.at > now - 60_000)
        .sort((a, b) => a.at - b.at)
        .slice(0, MAX_ALARMS);
    try {
        bridge.setTaskAlarms?.(JSON.stringify(items));
    } catch {
        // 桥异常绝不影响业务（旧壳没有这个方法时是空操作）
    }
}

/** 每个调度来源把自己那份待触发列表报上来；过期项在 flush 里统一过滤。 */
export function reportShellAlarms(kind: string, items: AlarmItem[]): void {
    buckets[kind] = items;
    flush();
}
