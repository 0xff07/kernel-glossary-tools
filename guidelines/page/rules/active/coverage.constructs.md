---
qa: manual
---

# Constructs

Cite every site that exhibits a behavior, with a location link at the mention and the sites the walkthrough explains as excerpts; when the set is too large, cite a representative spread and state the total. Cover:
 - the structs, enums and typedefs that hold the state and the helpers that allocate, initialize, read, modify and destroy them;
 - the lifecycle in full: allocation, initialization, teardown order, serializing locks, reference counting with the put that frees, state transitions and their drivers, notification mechanisms, deferred work and the ordering between them;
 - every hard-coded limit (timeout, retry count, error cap, buffer or queue size, poll or backoff interval) with its value, its defining symbol or literal and its file and line, reproduced where it governs a walked path.

