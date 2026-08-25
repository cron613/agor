# The Agor Language

Agor is a small, dynamically-typed, Python-like scripting language. Blocks are
delimited by indentation (not braces), statements are typically one per line,
and there is no static type system — a variable can hold any type and can be
reassigned to a different type at any time.

This document describes the language as implemented by the lexer, parser,
compiler, and VM in this repository. It only describes what's actually
implemented — see `examples/` for complete runnable programs.

## Lexical structure

- **Comments** start with `#` and run to end of line.
- **Indentation is significant.** A block is opened by a trailing `:` on the
  header line (`if ...:`, `func ...:`, `while ...:`, `for ...:`) and consists
  of the following more-deeply-indented lines, exactly like Python.
- Statements end at a newline; an expression may be split across multiple
  lines while inside unclosed `(`, `[`, or `{`.
- Identifiers are `[A-Za-z_][A-Za-z0-9_]*`. Keywords (cannot be used as
  identifiers): `func if elif else while for in return true false none and
  or not break continue`.

## Values and types

| Type | Literals / construction | Notes |
|---|---|---|
| `none` | `none` | the absence of a value |
| `bool` | `true`, `false` | |
| `int` | `42`, `-7` | 64-bit signed; arithmetic overflow is a runtime error |
| `float` | `3.14` | |
| `string` | `"hello"` | concatenate with `+` |
| `list` | `[1, 2, 3]` | ordered, heterogeneous, mutable |
| `dict` | `{"a": 1, "b": 2}` | insertion-ordered keys; keys must be hashable (`int`, `float`, `string`, `bool`, `none`) |
| `range` | `range(stop)`, `range(start, stop)`, `range(start, stop, step)` | lazily produced, mainly meant for `for ... in range(...)` |
| function | `func name(...): ...` | first-class value; `type(f)` reports `"function"` |

`type(x)` returns a value's type name as a string; `str(x)` renders it the
way `print` does.

## Variables and assignment

There is no declaration keyword — assigning to a name creates it:

```agor
x = 1
x = "now a string"
nums[0] = 99          # index assignment
info["key"] = "value" # dict index assignment
```

At the top level, every assigned name is a **global**. Inside a `func` body,
any name assigned *anywhere* in that function (including inside nested `if`
/`while`/`for` blocks) is a **local** for the function's entire body — this
matches Python's scoping rule, including the gotcha that assigning to a name
later in a function makes every earlier reference to that name in the same
function refer to the (not-yet-assigned) local, not an outer global.

## Operators

Arithmetic: `+ - * / % ` and unary `-`.
- `+` also does string concatenation (`"a" + "b"`) and list concatenation
  (`[1] + [2]` → `[1, 2]`).
- `/` returns an `int` when the division is exact, otherwise a `float`
  (`4 / 2` → `2`, `5 / 2` → `2.5`).
- `%` is modulo; division/modulo by zero and integer overflow are runtime
  errors, not silent wraparound.

Comparison: `== != < > <= >=` (numbers compare by value across `int`/`float`;
strings compare lexicographically).

Logical: `and`, `or`, `not` — `and`/`or` short-circuit and evaluate to one of
their operands (not necessarily a `bool`), the same as Python.

Indexing/attributes: `x[i]`, `x.attr`, negative list/string indices count
from the end (`xs[-1]` is the last element).

## Control flow

```agor
if cond:
    ...
elif other_cond:
    ...
else:
    ...

while cond:
    ...
    if done:
        break
    continue

for x in iterable:
    ...
```

`for` accepts a `list`, a `dict` (iterates its keys), a `string` (iterates
its characters), or a `range(...)`. `break` and `continue` behave as usual
and are only valid inside `while`/`for`.

## Functions

```agor
func fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
```

- Functions are declared with `func` and can only be declared at the top
  level (no nested `func` inside another function).
- `return` with no value (or falling off the end of the function body)
  yields `none`.
- Calling with the wrong number of arguments is a runtime error — there are
  no default/optional parameters or varargs.
- Recursion is supported up to a depth of 3000 calls, beyond which it's a
  catchable runtime error rather than a crash.

## Lists and dicts

```agor
nums = [1, 2, 3]
nums.push(4)        # append
last = nums.pop()   # remove & return the last element
len(nums)

info = {"name": "Agor", "year": 2026}
info.set("lang", true)     # info["lang"] = true also works
info.get("year")           # -> 2026
info.get("missing", "n/a") # default if key absent
info.keys()                 # -> a list of keys, insertion order
```

Indexing (`nums[0]`, `info["name"]`) works for both reading and assignment.
A missing dict key raises a runtime error on `d[key]`; use `.get(key,
default)` to avoid that.

## Built-in functions

| Function | Description |
|---|---|
| `print(...)` | writes its arguments space-separated, then a newline |
| `len(x)` | length of a `list`, `dict`, or `string` |
| `range(stop)` / `range(start, stop)` / `range(start, stop, step)` | integer range, exclusive of `stop` |
| `random(max)` / `random(min, max)` | random `int` in `[0, max)` or `[min, max]` |
| `input(prompt?)` | reads one line from stdin (or a browser `prompt()` in the WASM playground), returns `""` at EOF |
| `str(x)` / `int(x)` / `float(x)` | type conversion (string parsing errors are runtime errors) |
| `type(x)` | the value's type name as a string |
| `clock()` | seconds since the Unix epoch, as a `float`; used for timing (see `bench/fib_bench.agor`) |

## What Agor does *not* have

No classes/objects, no modules or `import`, no exceptions/`try`/`catch` (a
runtime error simply halts the program with a source line and message), no
closures/lambdas, no string formatting beyond `+` concatenation and `str()`,
no default or variadic function parameters.

## Errors

Every runtime failure is reported as `line N: <message>` and stops
execution — there's no way to catch or recover from one inside an Agor
program.

## Static checking

`agor check <file.agor>` analyzes a program without compiling or running
it, and reports *every* issue it finds in one pass (not just the first):

```
$ agor check bad.agor
line 5:17: error: undefined name 'nam'
line 11:9: warning: unreachable code
line 13:13: error: add() takes 2 argument(s) but 3 were given
agor: 2 error(s), 1 warning(s)
```

It stays true to Agor being dynamically typed — it never reasons about what
type a value holds — but it does catch things that are structurally wrong
no matter what runs: undefined names, wrong argument counts, `break`/
`continue` outside a loop, duplicate parameters, nested `func`, and
unreachable code. Exits non-zero only if it found at least one error
(warnings alone exit `0`).
