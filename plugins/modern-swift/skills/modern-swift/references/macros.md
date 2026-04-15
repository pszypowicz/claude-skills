# Swift Macros

Covers generic macro usage - `#Preview` and the five macro roles. All
examples compile-tested against the Xcode 26 toolchain.

The `@Observable` macro is **not** covered here. It has subtle isolation
and observation-tracking rules that live in the `swift-concurrency`
skill's `observable.md`.

## preview

`#Preview` is a freestanding declaration macro that generates SwiftUI
previews for the Xcode canvas.

```swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        Text("Hello")
    }
}

// Default preview
#Preview {
    ContentView()
}

// Named preview
#Preview("Dark Mode") {
    ContentView()
        .preferredColorScheme(.dark)
}

// With preview traits (device, orientation, sizing)
#Preview("Landscape", traits: .landscapeLeft) {
    ContentView()
}
```

`#Preview` replaces the older `PreviewProvider` protocol. There is no
reason to use `PreviewProvider` in new code - `#Preview` is simpler,
composes better, and supports traits natively.

### Tips

- Put `#Preview` at file scope below the view it previews. It works inside
  a nested scope but the convention is top-level.
- Preview closures can do quick setup (`let vm = ViewModel(); vm.seed()`)
  before returning the view. Keep it synchronous - previews do not support
  `async` setup directly.
- Use multiple `#Preview` blocks in the same file to preview light/dark,
  different data states, and different devices side-by-side.

## custom macros

Swift macros are compile-time source transformations implemented in a
separate compiler plugin target using SwiftSyntax. They run only at build
time and have no runtime cost.

### Macro roles

| Role                      | Form                              | Produces                                         |
| ------------------------- | --------------------------------- | ------------------------------------------------ |
| Freestanding expression   | `#macroName(args)`                | A value used as an expression                    |
| Freestanding declaration  | `#macroName(args)`                | One or more declarations (at file or type scope) |
| Attached peer             | `@MacroName`                      | Declarations added alongside the attached decl   |
| Attached member           | `@MacroName` on a type            | Declarations added inside the attached type      |
| Attached accessor         | `@MacroName` on a stored property | Get/set/willSet/didSet on the property           |
| Attached member-attribute | `@MacroName` on a type            | Attributes added to existing members             |
| Attached extension        | `@MacroName` on a type            | Extensions (including protocol conformances)     |

A single macro can declare multiple roles - for example, Observation's
`@Observable` is both a member macro (adds storage) and a member-attribute
macro (adds observation tracking to properties).

### Built-in freestanding macros

```swift
// #warning - emits a build-time warning
func todo() {
    // Uncomment to see the warning fire:
    // #warning("Remove before shipping")
}

// #error - fails the build with a custom message (handy in #if blocks)
#if NEVER_DEFINED
#error("This branch should never compile")
#endif

// File/line/function info
let here = #file
let line = #line
let fn = #function
```

`#warning`, `#error`, `#file`, `#line`, `#function`, `#filePath`,
`#fileID`, `#column`, `#dsohandle`, `#sourceLocation` are all built into
the standard library. Third-party packages add macros like `#URL` and
`@AddCodingKeys` via `swift-syntax`.

### Authoring a macro

The snippets below are illustrative fragments from a multi-target
SwiftPM package. They are not standalone-compilable because they
depend on `swift-syntax` and a `.macro` plugin target. Code blocks use
`text` so the build doesn't try to compile them.

A macro has two parts:

1. **Declaration** in your main target. References an external macro
   implementation by module + type name:

   ```text
   @freestanding(expression)
   public macro URL(_ string: String) -> Foundation.URL = #externalMacro(
       module: "MyMacrosPlugin",
       type: "URLMacro"
   )
   ```

2. **Implementation** in a compiler plugin target, conforming to one of
   the protocols from `SwiftSyntaxMacros`:

   ```text
   import SwiftSyntax
   import SwiftSyntaxMacros

   public struct URLMacro: ExpressionMacro {
       public static func expansion(
           of node: some FreestandingMacroExpansionSyntax,
           in context: some MacroExpansionContext
       ) throws -> ExprSyntax {
           // Validate arguments, produce expanded syntax
           return "URL(string: \"...\")!"
       }
   }
   ```

The plugin target is declared with `.macro` in `Package.swift`:

```text
.macro(
    name: "MyMacrosPlugin",
    dependencies: [
        .product(name: "SwiftSyntax", package: "swift-syntax"),
        .product(name: "SwiftSyntaxMacros", package: "swift-syntax"),
        .product(name: "SwiftCompilerPlugin", package: "swift-syntax"),
    ]
)
```

### When to reach for a macro

- **Good fit**: compile-time validation of literals, boilerplate generation
  (Codable keys, mock conformances), diagnostics that improve on runtime
  asserts.
- **Bad fit**: logic that depends on runtime state, code that would read
  more clearly as a function or generic, one-off transformations. Macros
  add a compile-time dependency on SwiftSyntax and slow incremental builds
  for consumers.

### Debugging macro expansions

In Xcode, right-click a macro call site and choose "Expand Macro" to see
what the macro produced. On the command line,
`swift build -Xswiftc -Xfrontend -Xswiftc -dump-macro-expansions` prints
the expansion for every macro in a build.
