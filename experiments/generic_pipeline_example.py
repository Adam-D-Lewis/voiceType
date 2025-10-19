#!/usr/bin/env python3
"""
Self-contained example of a generic pipeline that handles both:
1. Functions that return the entire result at once
2. Generator functions that yield outputs one at a time
3. Per-stage blocking configuration (some stages can block, others stream)
"""

from typing import Any, Callable, Generator, Iterator, Tuple, Union


class PipelineStage:
    """Wrapper for a pipeline stage with blocking configuration."""

    def __init__(self, func: Callable, blocking: bool = False):
        """
        Initialize a pipeline stage.

        Args:
            func: The processing function (regular or generator)
            blocking: If True, wait for all outputs before passing to next stage.
                     If False, stream outputs to next stage as they arrive.
        """
        self.func = func
        self.blocking = blocking

    def __repr__(self):
        mode = "blocking" if self.blocking else "streaming"
        return f"PipelineStage({self.func.__name__}, {mode})"


class Pipeline:
    """Generic pipeline that can handle both regular functions and generators."""

    def __init__(self, *stages: Union[Callable, PipelineStage]):
        """
        Initialize pipeline with a series of processing stages.

        Args:
            stages: Either callable functions or PipelineStage objects.
                   Plain functions default to streaming mode.
        """
        self.stages = []
        for stage in stages:
            if isinstance(stage, PipelineStage):
                self.stages.append(stage)
            else:
                # Default to streaming for plain functions
                self.stages.append(PipelineStage(stage, blocking=False))

    def execute(self, input_data: Any) -> Iterator[Any]:
        """
        Execute the pipeline on input data.
        Yields results incrementally as they become available.
        Respects per-stage blocking configuration.
        """
        current = input_data

        for stage in self.stages:
            print(f"  [Pipeline] Executing {stage}")

            # Execute the stage function
            result = stage.func(current)

            # Check if result is a generator
            if isinstance(result, Generator):
                if stage.blocking:
                    # Blocking mode: collect all results before proceeding
                    print(f"  [Pipeline] Blocking stage - collecting all outputs...")
                    accumulated = list(result)
                    current = accumulated
                    yield current
                else:
                    # Streaming mode: yield as results arrive
                    print(
                        f"  [Pipeline] Streaming stage - passing outputs incrementally..."
                    )
                    accumulated = []
                    for item in result:
                        accumulated.append(item)
                        yield item
                    current = accumulated
            else:
                # Regular function - pass result to next stage
                current = result
                yield current

    def execute_blocking(self, input_data: Any) -> Any:
        """
        Execute the pipeline and return only the final result.
        Blocks until all stages complete.
        """
        results = list(self.execute(input_data))
        return results[-1] if results else None


# Example processing functions


def load_data(file_path: str) -> list:
    """Regular function: returns entire result at once."""
    print(f"[load_data] Loading from {file_path}")
    return ["apple", "banana", "cherry", "date", "elderberry"]


def process_items_generator(items: list) -> Generator[str, None, None]:
    """Generator function: yields processed items one at a time."""
    print("[process_items_generator] Starting to process items...")
    for item in items:
        processed = item.upper()
        print(f"[process_items_generator] Yielding: {processed}")
        yield processed


def filter_items(items: list) -> list:
    """Regular function: filters items and returns all at once."""
    print(f"[filter_items] Filtering {len(items)} items")
    filtered = [item for item in items if len(item) > 5]
    print(f"[filter_items] Kept {len(filtered)} items")
    return filtered


def add_prefix_generator(items: list) -> Generator[str, None, None]:
    """Generator function: adds prefix to each item incrementally."""
    print("[add_prefix_generator] Adding prefixes...")
    for i, item in enumerate(items, 1):
        result = f"#{i}: {item}"
        print(f"[add_prefix_generator] Yielding: {result}")
        yield result


def main():
    print("=" * 60)
    print("Example 1: All streaming stages")
    print("=" * 60)

    # All stages stream - results flow through immediately
    pipeline = Pipeline(
        PipelineStage(load_data, blocking=False),
        PipelineStage(process_items_generator, blocking=False),
        PipelineStage(filter_items, blocking=False),
        PipelineStage(add_prefix_generator, blocking=False),
    )

    print("\n--- Streaming Execution ---")
    for result in pipeline.execute("data.txt"):
        print(f">>> Received: {result}")

    print("\n" + "=" * 60)
    print("Example 2: Mixed blocking and streaming stages")
    print("=" * 60)

    # Generator is BLOCKING - waits for all items before filtering
    # This shows blocking at the stage level
    pipeline2 = Pipeline(
        PipelineStage(load_data, blocking=False),
        PipelineStage(process_items_generator, blocking=True),  # Block here!
        PipelineStage(filter_items, blocking=False),
        PipelineStage(add_prefix_generator, blocking=False),  # Stream here
    )

    print("\n--- Mixed Execution ---")
    for result in pipeline2.execute("data.txt"):
        print(f">>> Received: {result}")

    print("\n" + "=" * 60)
    print("Example 3: Streaming then blocking pattern")
    print("=" * 60)

    def generate_numbers() -> Generator[int, None, None]:
        """Generate numbers 1-5."""
        print("  [generate_numbers] Generating...")
        for i in range(1, 6):
            print(f"  [generate_numbers] Yielding {i}")
            yield i

    def square_generator(numbers: list) -> Generator[int, None, None]:
        """Square each number."""
        print(f"  [square_generator] Squaring {len(numbers)} numbers")
        for n in numbers:
            result = n**2
            print(f"  [square_generator] Yielding {n}^2 = {result}")
            yield result

    def sum_all(numbers: list) -> int:
        """Sum all numbers (regular blocking function)."""
        result = sum(numbers)
        print(f"  [sum_all] Sum of {numbers} = {result}")
        return result

    # Stream numbers, block on squares, then sum
    pipeline3 = Pipeline(
        PipelineStage(lambda _: generate_numbers(), blocking=False),  # Stream
        PipelineStage(square_generator, blocking=True),  # Block
        PipelineStage(sum_all, blocking=False),  # Regular function
    )

    print("\n--- Streaming then Blocking Execution ---")
    for result in pipeline3.execute(None):
        print(f">>> Received: {result}")

    print("\n" + "=" * 60)
    print("Example 4: Using plain functions (default streaming)")
    print("=" * 60)

    # Can mix PipelineStage objects with plain functions
    pipeline4 = Pipeline(
        load_data,  # Plain function (streaming)
        PipelineStage(process_items_generator, blocking=True),  # Explicit blocking
        filter_items,  # Plain function (streaming)
    )

    print("\n--- Mixed Syntax Execution ---")
    for result in pipeline4.execute("data.txt"):
        print(f">>> Received: {result}")


if __name__ == "__main__":
    main()
