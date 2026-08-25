import time

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

print("=== Python fib(36) Benchmark ===")

start = time.perf_counter()

result = fib(36)

elapsed = time.perf_counter() - start

print("result =", result)
print("time =", elapsed)
