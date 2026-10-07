"""进程内滑动窗口限流器（公开版安全补丁 S-2 / H-3）。

设计：
- 零第三方依赖；key -> 单调时间戳列表；每次 check 做窗口内裁剪。
- 单进程内存实现：多 worker / 多实例部署时，请在网关层（Nginx limit_req）
  或 Redis 层面做全局限流，此处仅为应用层纵深。
- 线程安全：CPython GIL 下 list 操作原子；check 内的"读-改-写"在
  asyncio 单线程事件循环内执行，无并发交错。

策略（公开版基线）：
- forgot-password：5 次 / 10 分钟 / IP+phone —— 防短信费用攻击与号段横扫。
- reset-password：20 次 / 10 分钟 / IP+phone —— 6 位重置码仅 100 万空间，
  此为防在线爆破的主防线；纵深另有 _ResetCodeStore 的连续失败计数
  （10 次作废当前 code），两者阈值错开以便分别测试。
- ws_handshake：20 次 / 分钟 / IP —— H-3：WS 握手在 accept 之前限流，
  防未认证连接洪水。
"""
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


POLICY_FORGOT_PASSWORD = RateLimitPolicy("forgot_password", 5, 600)
POLICY_RESET_PASSWORD = RateLimitPolicy("reset_password", 20, 600)
POLICY_WS_HANDSHAKE = RateLimitPolicy("ws_handshake", 20, 60)


class InMemoryRateLimiter:
    """滑动窗口计数器。check() 返回 True=放行（已计数），False=超限。"""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, policy: RateLimitPolicy) -> bool:
        now = time.monotonic()
        cutoff = now - policy.window_seconds
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        if len(hits) >= policy.limit:
            self._hits[key] = hits  # 裁剪后写回，避免无界增长
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def reset(self) -> None:
        """仅测试用：清空全部计数。"""
        self._hits.clear()


limiter = InMemoryRateLimiter()
