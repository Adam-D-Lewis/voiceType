import threading
import time
from dataclasses import dataclass

VERBOSE_PRINT = False


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
    # UNLOCKED READER: reads state without locking
    # This is UNSAFE as it may read inconsistent state
    def state(self) -> CompositeState:
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
            if VERBOSE_PRINT:
                # Print the state after updating
                self._state = CompositeState(a=cur.a, b=cur.a + 1)


class WriterAndReaderLocked:
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
            if VERBOSE_PRINT:
                # Print the state after updating
                self._state = CompositeState(a=cur.a, b=cur.a + 1)


def run_test(StateClass, duration=2.0, num_readers=8):
    instance = StateClass()
    stop_readers_flag = threading.Event()
    anomalies = 0
    non_anomalies = 0
    threads = []

    def writer():
        # while not stop:
        instance.bump()

    def reader():
        nonlocal anomalies, non_anomalies
        while not stop_readers_flag.is_set():
            state = instance.state  # May be unlocked depending on class
            # Check invariant: b must always be a + 1
            if state.b != state.a + 1:
                if VERBOSE_PRINT:
                    # Print the inconsistent state for debugging
                    print(f"Anomalous state detected: {state}")
                anomalies += 1
            else:
                if VERBOSE_PRINT:
                    print(f"Consistent state: {state}")
                non_anomalies += 1

    for _ in range(num_readers):
        rt = threading.Thread(target=reader, daemon=True)
        rt.start()
        threads.append(rt)

    start_time = time.time()
    while time.time() - start_time < duration:
        writer()

    stop_readers_flag.set()

    for th in threads:
        th.join()

    return anomalies, non_anomalies


if __name__ == "__main__":
    print("Running with unlocked reader (expect anomalies)...")
    anomalies_unlocked, non_anomalies_unlocked = run_test(
        WriterLockedReaderUnlocked, duration=0.1, num_readers=8
    )
    print(
        f"Anomalies/Non-anomalies (unlocked reader): {anomalies_unlocked}/{non_anomalies_unlocked}"
    )

    print("Running with locked reader (expect no anomalies)...")
    anomalies_locked, non_anomalies_locked = run_test(
        WriterAndReaderLocked, duration=0.1, num_readers=8
    )
    print(
        f"Anomalies/Non-anomalies (locked reader): {anomalies_locked}/{non_anomalies_locked}"
    )
    print("Test completed.")
