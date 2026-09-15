# Swarm

Planned multi-drone functionality includes routing, relay, discovery, network
management, task allocation, cooperative exploration, formation control,
distributed map sharing/merging, conflict resolution, synchronization, and
ground-station swarm management.

No swarm runtime exists in this checkout. Add these areas as concrete work
arrives. Shared coordinate frames and synchronized timestamps must be established
before observations from multiple drones can be merged.

See the [swarm architecture and roadmap](../Docs/Architecture/system_overview.md).
Code executing directly on an ESP32 belongs in [ESP32_Code](../ESP32_Code/).
