import threading
import time
from dataclasses import dataclass


# A composite state with an invariant: b must always be a + 1
@dataclass
class CompositeState:
    a: int
    b: int


class WriterLockedReaderUnlocked:
    def __init__(self):
        # Start in a consistent state
        self._state = CompositeState(a=0, b=1)
        self._lock = threading.RLock()

    @property
    def state(self) -> CompositeState:
        with self._lock:
            return CompositeState(a=self._state.a, b=self._state.b)

    @state.setter
    def state(self, new_state: CompositeState):
        with self._lock:
            self._state = new_state

    def bump(self):
        # Simulate a multi-step update with invariant: b == a + 1 always
        with self._lock:
            # breakpoint()
            # Step 1: update a
            old = self._state
            self.state = CompositeState(a=old.a + 1, b=old.b)

            # Step 2: update b to preserve invariant
            time.sleep(0.00005)  # Simulate some processing time
            cur = self._state
            self.state = CompositeState(a=cur.a, b=cur.a + 1)
            print(f"State updated to: {self._state}")


def run_test(StateClass, duration=2.0, num_readers=8):
    instance = StateClass()
    stop = False
    anomalies = 0
    threads = []

    def writer():
        # while not stop:
        instance.bump()

    def reader():
        nonlocal anomalies
        while not stop:
            state = instance.state  # May be unlocked depending on class
            # Check invariant: b must always be a + 1
            if state.b != state.a + 1:
                print(f"Inconsistent state detected: {state}")
                anomalies += 1
            else:
                pass
                print(f"Consistent state: {state}")

    for _ in range(num_readers):
        rt = threading.Thread(target=reader, daemon=True)
        rt.start()
        threads.append(rt)

    start_time = time.time()
    while time.time() - start_time < duration:
        writer()

    for th in threads:
        th.join(timeout=0.2)

    return anomalies


if __name__ == "__main__":
    print("Running with unlocked reader (expect anomalies)...")
    anomalies_unlocked = run_test(
        WriterLockedReaderUnlocked, duration=0.1, num_readers=8
    )
    print(f"Anomalies (unlocked reader): {anomalies_unlocked}")
