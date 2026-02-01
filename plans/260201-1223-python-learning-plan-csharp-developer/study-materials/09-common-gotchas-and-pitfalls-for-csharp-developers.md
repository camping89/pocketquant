# Common Gotchas & Pitfalls for C# Developers

## 1. Mutable Default Arguments

### The Bug

```python
# ❌ DANGEROUS - Default list is SHARED across calls!
def add_item(item, items=[]):
    items.append(item)
    return items

# First call
result1 = add_item("a")  # ["a"]

# Second call - WHERE'S "a" COMING FROM?!
result2 = add_item("b")  # ["a", "b"] ← BUG!
```

### Why It Happens

```
Python evaluates default arguments ONCE at function definition time.
The same list object is reused for every call.

                  ┌─────────────┐
Function defined: │ items = []  │ ← One list created
                  └─────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     │                   │                   │
     ▼                   ▼                   ▼
  Call 1              Call 2              Call 3
  items = []          items = ["a"]       items = ["a","b"]
  append("a")         append("b")         append("c")
```

### The Fix

```python
# ✅ CORRECT - Use None as sentinel
def add_item(item, items=None):
    if items is None:
        items = []  # New list each call
    items.append(item)
    return items
```

---

## 2. `is` vs `==`

### The Bug

```python
# ❌ WRONG - Comparing identity, not equality
a = [1, 2, 3]
b = [1, 2, 3]
if a is b:  # False! Different objects
    print("equal")

# ❌ WRONG - Works by accident with small ints
x = 256
y = 256
if x is y:  # True (Python caches small ints)
    print("equal")

x = 1000
y = 1000
if x is y:  # False! Not cached
    print("equal")
```

### The Rule

```python
# ✅ Use == for VALUE comparison
if a == b:  # True - same values

# ✅ Use is ONLY for None, True, False
if value is None:
if flag is True:
if result is not None:
```

---

## 3. Integer Division

### The Bug

```python
# ❌ SURPRISE - Division returns float!
result = 5 / 2  # 2.5, not 2!

# C# behavior:
# int / int = int (5 / 2 = 2)
```

### The Fix

```python
# ✅ Use // for integer division
result = 5 // 2  # 2

# ✅ Use divmod for both quotient and remainder
quotient, remainder = divmod(5, 2)  # (2, 1)
```

---

## 4. Truthiness Gotchas

### The Bug

```python
# ❌ Empty collections are falsy!
items = []
if items:  # False - empty list is falsy
    process(items)

# ❌ Zero is falsy!
count = 0
if count:  # False!
    print(f"Count: {count}")

# ❌ Empty string is falsy!
name = ""
if name:  # False!
    greet(name)
```

### Falsy Values in Python

```
False, None, 0, 0.0, "", [], {}, set(), ()
```

### When You Need Explicit Checks

```python
# ✅ Explicit length check when 0 is valid
if len(items) > 0:
    process(items)

# ✅ Explicit None check when 0 is valid
if count is not None:
    print(f"Count: {count}")

# ✅ Explicit empty string check
if name != "":
    greet(name)
```

---

## 5. Shallow Copy Trap

### The Bug

```python
# ❌ Assignment copies REFERENCE, not object
original = [1, 2, [3, 4]]
copy = original  # Same object!

copy.append(5)
print(original)  # [1, 2, [3, 4], 5] ← Modified!
```

```python
# ❌ Shallow copy doesn't copy nested objects
import copy as copy_module

original = [1, 2, [3, 4]]
shallow = original.copy()  # or list(original)

shallow[2].append(5)
print(original)  # [1, 2, [3, 4, 5]] ← Nested modified!
```

### The Fix

```python
import copy

# ✅ Deep copy for nested structures
original = [1, 2, [3, 4]]
deep = copy.deepcopy(original)

deep[2].append(5)
print(original)  # [1, 2, [3, 4]] ← Unchanged!
```

---

## 6. Variable Scope in Loops

### The Bug

```python
# ❌ Lambda captures variable, not value!
functions = []
for i in range(3):
    functions.append(lambda: print(i))

for f in functions:
    f()  # Prints: 2, 2, 2 (not 0, 1, 2!)
```

### Why It Happens

```
Lambda captures reference to 'i', not value.
When lambdas execute, i = 2 (last value).
```

### The Fix

```python
# ✅ Capture value with default argument
functions = []
for i in range(3):
    functions.append(lambda x=i: print(x))  # x captures i's VALUE

for f in functions:
    f()  # Prints: 0, 1, 2
```

---

## 7. Class vs Instance Variables

### The Bug

```python
# ❌ Class variable shared across ALL instances!
class Counter:
    count = 0  # Class variable

    def increment(self):
        Counter.count += 1  # Modifies class, not instance

c1 = Counter()
c2 = Counter()

c1.increment()
print(c2.count)  # 1 ← Shared!
```

### The Fix

```python
# ✅ Instance variable in __init__
class Counter:
    def __init__(self):
        self.count = 0  # Instance variable

    def increment(self):
        self.count += 1

c1 = Counter()
c2 = Counter()

c1.increment()
print(c2.count)  # 0 ← Independent!
```

---

## 8. String Formatting Gotchas

### The Bug

```python
# ❌ % formatting with tuple confusion
name = "Alice"
message = "Hello, %s" % name  # Works

data = ("Alice", 30)
message = "Name: %s" % data  # TypeError! Interpreted as 2 args
```

### The Fix

```python
# ✅ Use f-strings (Python 3.6+)
message = f"Hello, {name}"
message = f"Name: {data}"

# ✅ Or explicit tuple
message = "Name: %s" % (data,)  # Note trailing comma
```

---

## 9. Exception Handling Scope

### The Bug

```python
# ❌ Exception variable deleted after except block!
try:
    raise ValueError("test")
except ValueError as e:
    error = e

print(error)  # Works in Python 3, but...

# In except block:
try:
    raise ValueError("test")
except ValueError as e:
    pass

print(e)  # NameError: 'e' is not defined
```

### The Fix

```python
# ✅ Store before block ends
error = None
try:
    raise ValueError("test")
except ValueError as e:
    error = e

print(error)  # Works
```

---

## 10. Import Side Effects

### The Bug

```python
# module_a.py
print("Module A loaded!")  # Runs on import!
value = expensive_computation()  # Runs on import!

# main.py
import module_a  # "Module A loaded!" + computation runs!
```

### The Fix

```python
# ✅ Guard execution with __name__ check
# module_a.py
def expensive_computation():
    ...

if __name__ == "__main__":
    # Only runs when executed directly, not imported
    print("Running as script")
    result = expensive_computation()
```

---

## 11. Datetime Timezone Gotchas

### The Bug

```python
from datetime import datetime

# ❌ Naive datetime - no timezone info!
now = datetime.now()  # Local time, but no TZ info

# ❌ Comparing naive and aware datetimes
from datetime import timezone
aware = datetime.now(timezone.utc)
naive = datetime.now()

if aware > naive:  # TypeError!
    ...
```

### The Fix

```python
from datetime import datetime, timezone

# ✅ Always use timezone-aware datetimes
now = datetime.now(timezone.utc)

# ✅ Or use the UTC constant
from datetime import UTC  # Python 3.11+
now = datetime.now(UTC)
```

---

## 12. Dictionary Iteration During Modification

### The Bug

```python
# ❌ RuntimeError: dictionary changed size during iteration
data = {"a": 1, "b": 2, "c": 3}
for key in data:
    if data[key] < 2:
        del data[key]  # Modifying while iterating!
```

### The Fix

```python
# ✅ Create list of keys first
data = {"a": 1, "b": 2, "c": 3}
for key in list(data.keys()):  # Copy keys
    if data[key] < 2:
        del data[key]

# ✅ Or use dictionary comprehension
data = {k: v for k, v in data.items() if v >= 2}
```

---

## Quick Reference Card

| Gotcha | C# Behavior | Python Behavior | Fix |
|--------|-------------|-----------------|-----|
| Mutable default | N/A | Shared | Use `None` |
| Identity check | `==` for value | `is` for identity | Use `==` |
| Integer division | `int / int = int` | Returns `float` | Use `//` |
| Empty collections | Explicit check | Falsy | Explicit if needed |
| Copy | `.Clone()` | Reference | `copy.deepcopy()` |
| Loop variables | Value capture | Reference capture | Default arg |
| Class variables | Instance-like | Shared | Use `__init__` |
| Timezone | Explicit | Naive default | Use `UTC` |
