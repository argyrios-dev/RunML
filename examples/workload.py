import sys
import time

n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
data = [i * i for i in range(n)]
time.sleep(0.25)
print(sum(data))
