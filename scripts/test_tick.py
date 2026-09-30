import asyncio
from model.simulator import create_simulator_state
async def main():
    sim = create_simulator_state()
    await sim.refresh_live_now()
    print("Tambaram status initially:", sim.manager.get_station_status("AWS-CHN-101")["status"])
    sim.start_replay()
    await sim.tick()
    sim.manager.buffers["AWS-CHN-101"].health.status = "OFFLINE"
    print("Tambaram status during replay:", sim.manager.get_station_status("AWS-CHN-101")["status"])
    sim.stop_replay()
    print("Tambaram status right after stop:", sim.manager.get_station_status("AWS-CHN-101")["status"])
    await sim.tick()
    print("Tambaram status after live tick:", sim.manager.get_station_status("AWS-CHN-101")["status"])
if __name__ == "__main__":
    asyncio.run(main())
