# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Agor is a small, Python-like programming language implemented in Go: a hand-written lexer/parser, an AST, a compiler that lowers the AST to a custom bytecode, and a stack-based VM that executes it. It also ships a WebAssembly build (`wasm/`) with a TypeScript front end (`web/`) so the language can be tried in a browser.

## Commands

```sh
go build ./...                          # build everything
go build -o bin/agor.exe ./cmd/agor     # build the CLI (binary is gitignored)

go test ./...                           # run all tests (lexer, parser, vm)
go test ./internal/lexer/ -run TestName # run a single test
go test ./internal/vm/ -bench=BenchmarkFib -run=^$   # run a benchmark only
```

CLI usage (`agor <subcommand>`):
- `agor run <file.agor>` — parse, compile in memory, execute immediately
- `agor build <file.agor> [-o out.agorc]` — compile ahead of time to a bytecode file
- `agor exec <file.agorc>` — execute a previously built bytecode file
- `agor check <file.agor>` — static analysis only: report every issue (undefined names, arity mismatches, ...) without compiling or running
- `agor repl` — interactive shell

WASM playground build: `wasm/main.go` has `//go:build js && wasm`; build it with `GOOS=js GOARCH=wasm go build -o web/agor.wasm ./wasm`. The `web/` TypeScript front end is a separate npm project (`web/package.json`: `npm run typecheck`, `npm run build`).

`bench/fib_bench.agor` and `bench/fib_bench.py` are the same recursive-Fibonacci workload in both languages, used for cross-language performance comparison. `internal/vm/bench_test.go` has the Go-level `BenchmarkFib` used for profiling the VM itself (`-cpuprofile`/`-memprofile`).

## Architecture

Pipeline: `internal/lexer` → `internal/parser` (→ `internal/ast`) → `internal/compiler` → `internal/bytecode` (Chunk) → `internal/vm`. Both `agor run` (compile + execute in one process) and `agor build` + `agor exec` (compile now, execute later from a `.agorc` file) end up calling the same `vm.VM.Run` — there is exactly one execution path, not two. `internal/checker` taps the pipeline right after parsing, as an alternate consumer of the same `*ast.Program` (`agor check` never reaches the compiler or VM at all).

Every `ast.Stmt`'s `Base` (`Line`/`Col`) is set from the statement's leading token in `internal/parser` — this is what gives the compiler, the checker, and runtime errors an accurate source position; don't add a new statement constructor without setting it.

**Lexer** (`internal/lexer`): Python-style significant indentation. It synthesizes `INDENT`/`DEDENT`/`NEWLINE` tokens from leading whitespace, the same way Python's own tokenizer does, so the parser can stay a plain recursive-descent parser with no indentation-awareness of its own. It tracks bracket/paren nesting depth to suppress `NEWLINE` emission inside multi-line `(...)`/`[...]`/`{...}` expressions.

**Parser** (`internal/parser`): recursive descent with precedence climbing for expressions, producing the `internal/ast` node tree.

**Compiler** (`internal/compiler`): lowers a `*ast.Program` to a `*bytecode.Chunk`.
- Function-local scoping uses a *prescan* (`collectLocals`): every name assigned anywhere in a function's body (including in nested blocks) is treated as local to that function for its entire body, mirroring Python's scoping rule — not "declared at first assignment, global before that."
- Globals are addressed by slot index, not name, at runtime. `bytecode.GlobalTable` assigns each global name a stable slot shared by the top-level chunk and every function chunk that references it, so `OpLoadGlobal`/`OpStoreGlobal` are plain slice indexing rather than map lookups.
- `Compile` gives a program its own fresh `GlobalTable`. `CompileREPL` takes a caller-owned `GlobalTable` so a name defined in one REPL input keeps the same slot in later inputs, and — when the final statement is a bare expression — leaves its value on the stack instead of popping it, which is how the REPL echoes results.

**Bytecode** (`internal/bytecode`): flat `Instruction{Op, A, Line}` stream plus a constant pool and a name table (used by `OpGetAttr`). `Chunk.Write`/`Read` (de)serialize via `encoding/gob` to the `.agorc` format (magic `"AGORBC02"`), which is what makes ahead-of-time compilation possible.

**VM** (`internal/vm`): a stack-based interpreter (`VM.loop`). Two performance-critical, non-obvious design points:
- Call frames are a `[]frame` *value* slice (not `[]*frame`), and every frame's local variables live in one shared, growable arena slice (`vm.locals`) rather than a per-call `[]any`. A call reserves a window in the arena (`growLocals`) instead of heap-allocating fresh args/locals/frame objects; this eliminated ~8M allocations on a `fib(27)` run and is roughly a 7x speedup over the naive per-call-allocation version. Don't reintroduce a per-frame `[]any` or `*frame` heap allocation without a strong reason.
- Runtime values are plain Go `any`: `nil`→none, `int64`→int, `float64`→float, `string`, `bool`, `*List`, `*Dict`, `*Function` (user-defined), `*Builtin` (native function, also used for bound methods like `list.push`), `*RangeVal` (lazy `range()` sequence). `VM.MaxSteps` bounds total instructions executed (used by the WASM build to keep a runaway loop from freezing the browser tab); `MaxCallDepth` (3000) bounds recursion and turns what would otherwise be a fatal Go stack overflow into a catchable `RuntimeError`.

**Builtins** (`internal/builtins`): registers native globals (`print`, `len`, `range`, `random`, `input`, `str`, `int`, `float`, `clock`, `type`) into a `*vm.VM`. Deliberately kept out of package `vm` so the VM core has no I/O dependency; `cmd/agor` wires it to real stdout/stdin, `wasm/main.go` wires `input()` to a browser `prompt()` dialog instead since there's no real stdin in a browser tab.

**Checker** (`internal/checker`): static analysis over the raw `*ast.Program` — no compiler/bytecode/VM dependency, so it's cheap to run on every keystroke (e.g. from a future LSP). `Check` returns *every* issue in one pass (unlike the compiler, which stops at the first error). Agor stays dynamically typed on purpose: the checker does no type inference and never rejects code based on what a value's type *might* be — it only flags things that are wrong regardless of what runs (undefined names, `break`/`continue` outside a loop, duplicate params, nested `func`, unreachable code after `return`/`break`/`continue`). It mirrors the compiler's function-local-scoping prescan (`collectFuncLocals` ~ compiler's `collectLocals`) — keep the two in sync if that scoping rule ever changes. Argument-count checking (`funcArity`/`builtinArity`) is deliberately conservative: it only fires when a call's callee name is unambiguous (a bare top-level function never reassigned, or an unshadowed builtin) so a legitimately dynamic reassignment (`add = 5`) never produces a false positive. `builtinArity` is a hand-maintained mirror of `internal/builtins`' registrations — update both together.
