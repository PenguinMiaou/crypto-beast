#!/usr/bin/env python3
"""Clean up stale algo orders — keep only the latest SL per active position.

For symbols WITH open positions: keep only the most recent algo order, cancel the rest.
For symbols WITHOUT positions: cancel all algo orders.

Usage: source .venv/bin/activate && python scripts/cleanup_algo_orders.py
       Add --dry-run to preview without cancelling.
"""
import asyncio
import sys
import hmac
import hashlib
import time
import aiohttp
from pathlib import Path
from urllib.parse import urlencode
from collections import defaultdict
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rate_limiter import BinanceRateLimiter


async def main():
    dry_run = "--dry-run" in sys.argv

    env = dotenv_values(str(Path(__file__).parent.parent / ".env"))
    api_key = env.get("BINANCE_API_KEY", "")
    api_secret = env.get("BINANCE_API_SECRET", "")
    rate_limiter = BinanceRateLimiter()

    def sign(params):
        query = urlencode(params)
        sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return query, sig

    headers = {"X-MBX-APIKEY": api_key}

    async with aiohttp.ClientSession() as session:
        # Step 1: Get open positions
        pos_params = {"timestamp": int(time.time() * 1000)}
        q, s = sign(pos_params)
        await rate_limiter.acquire_order_slot()
        async with session.get(f"https://fapi.binance.com/fapi/v2/account?{q}&signature={s}",
                               headers=headers) as resp:
            if resp.status != 200:
                print(f"Failed to query account: {await resp.text()}")
                return
            account = await resp.json()

        open_positions = set()  # (symbol, positionSide) tuples
        for pos in account.get("positions", []):
            amt = float(pos.get("positionAmt", 0))
            if amt != 0:
                open_positions.add((pos["symbol"], pos["positionSide"]))

        print(f"Open positions: {open_positions or 'none'}")

        # Step 2: Get all open algo orders
        algo_params = {"timestamp": int(time.time() * 1000)}
        q, s = sign(algo_params)
        await rate_limiter.acquire_order_slot()
        async with session.get(f"https://fapi.binance.com/fapi/v1/openAlgoOrders?{q}&signature={s}",
                               headers=headers) as resp:
            if resp.status != 200:
                print(f"Failed to query algo orders: {await resp.text()}")
                return
            data = await resp.json()

        orders = data if isinstance(data, list) else data.get("orders", [])
        print(f"Total open algo orders: {len(orders)}")

        # Step 3: Group by symbol+positionSide, sort by createTime
        groups = defaultdict(list)  # type: ignore
        for o in orders:
            key = (o.get("symbol"), o.get("positionSide"))
            groups[key].append(o)

        to_cancel = []
        to_keep = []

        for (sym, pos_side), sym_orders in groups.items():
            # Sort by createTime descending (newest first)
            sym_orders.sort(key=lambda x: x.get("createTime", 0), reverse=True)

            if (sym, pos_side) in open_positions:
                # Keep only the newest one, cancel the rest
                to_keep.append(sym_orders[0])
                to_cancel.extend(sym_orders[1:])
            else:
                # No open position — cancel all
                to_cancel.extend(sym_orders)

        print(f"\nKeeping: {len(to_keep)} (latest SL per active position)")
        for o in to_keep:
            print(f"  KEEP: {o.get('symbol')} {o.get('positionSide')} "
                  f"triggerPrice={o.get('triggerPrice')} algoId={o.get('algoId')}")

        print(f"\nCancelling: {len(to_cancel)} stale orders")

        if dry_run:
            print("\n[DRY RUN] No orders cancelled.")
            for o in to_cancel[:10]:
                print(f"  Would cancel: {o.get('symbol')} {o.get('positionSide')} "
                      f"triggerPrice={o.get('triggerPrice')} algoId={o.get('algoId')}")
            if len(to_cancel) > 10:
                print(f"  ... and {len(to_cancel) - 10} more")
            return

        # Step 4: Cancel stale orders
        cancelled = 0
        for o in to_cancel:
            algo_id = o.get("algoId")
            if not algo_id:
                continue
            cancel_params = {"algoId": algo_id, "timestamp": int(time.time() * 1000)}
            q, s = sign(cancel_params)
            curl = f"https://fapi.binance.com/fapi/v1/algoOrder?{q}&signature={s}"
            await rate_limiter.acquire_order_slot()
            async with session.delete(curl, headers=headers) as cresp:
                if cresp.status == 200:
                    cancelled += 1
                else:
                    print(f"  Failed: algoId={algo_id}: {await cresp.text()}")

        print(f"\nDone! Cancelled {cancelled}/{len(to_cancel)} stale algo orders.")
        print(f"Remaining: {len(to_keep)} active SL orders.")


if __name__ == "__main__":
    asyncio.run(main())
