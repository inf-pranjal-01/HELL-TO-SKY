"""Temporary deterministic replay smoke check; safe to run locally."""
import asyncio
from pathlib import Path

from history_store import HistoryStore
from model.simulator import create_simulator_state


async def main():
    sim = create_simulator_state()
    # Never touch the dashboard's real audit CSVs during a smoke check.
    sim.manager.history = HistoryStore(Path(__file__).parent / "data" / "_smoke_history")
    try:
        sim.start_replay()
        # The original crash was at cursor 18; twenty-five ticks cross it.
        for step in range(25):
            try:
                await sim.tick()
            except Exception:
                print(f"FAILED replay cursor={sim._replay_cursor_idx}, step={step}")
                raise
        print(f"PASS cursor={sim._replay_cursor_idx} latest={len(sim.latest)}")
    finally:
        await sim.close()


if __name__ == "__main__":
    asyncio.run(main())
