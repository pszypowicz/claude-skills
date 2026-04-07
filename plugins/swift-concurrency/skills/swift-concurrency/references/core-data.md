# Core Data and Swift Concurrency

## NSManagedObject and Sendability

`NSManagedObject` is **not Sendable** and is tied to its `NSManagedObjectContext`'s queue. Passing managed objects across isolation boundaries is unsafe and will produce compiler warnings or errors under strict concurrency checking.

### Pass NSManagedObjectID

`NSManagedObjectID` is thread-safe and can cross boundaries:

```swift
actor DataStore {
    private let container: NSPersistentContainer

    func fetchUserID(named name: String) async throws -> NSManagedObjectID {
        try await container.viewContext.perform {
            let request = User.fetchRequest()
            request.predicate = NSPredicate(format: "name == %@", name)
            guard let user = try container.viewContext.fetch(request).first else {
                throw DataError.notFound
            }
            return user.objectID
        }
    }
}

// On MainActor, re-fetch the object in the correct context
@MainActor
func displayUser(id: NSManagedObjectID) {
    let user = viewContext.object(with: id) as! User
    nameLabel.text = user.name
}
```

### Pass Sendable DTOs

Create plain `Sendable` structs to transfer data:

```swift
struct UserDTO: Sendable {
    let id: NSManagedObjectID
    let name: String
    let email: String
    let createdAt: Date
}

extension User {
    func toDTO() -> UserDTO {
        UserDTO(
            id: objectID,
            name: name ?? "",
            email: email ?? "",
            createdAt: createdAt ?? .distantPast
        )
    }
}

actor DataStore {
    func fetchAllUsers() async throws -> [UserDTO] {
        try await context.perform {
            let request = User.fetchRequest()
            let users = try self.context.fetch(request)
            return users.map { $0.toDTO() }
        }
    }
}
```

This is the recommended pattern. The DTO crosses actor boundaries safely.

---

## perform / performAndWait Async Variants

`NSManagedObjectContext` provides async-friendly `perform` methods:

```swift
// Async perform — suspends the calling task, runs on the context's queue
let users = try await context.perform {
    let request = User.fetchRequest()
    return try context.fetch(request)
}

// Scheduled perform with options
try await context.perform(schedule: .enqueued) {
    let user = User(context: context)
    user.name = "Alice"
    try context.save()
}
```

`schedule` options:
- `.immediate` — executes immediately if already on the correct queue (like `performAndWait`), otherwise enqueues
- `.enqueued` — always enqueues (like `perform`)

### Important: Return Values Must Be Sendable

The closure passed to `perform` should return `Sendable` types. Returning an `NSManagedObject` from `perform` is unsafe because the object will be accessed off its context's queue:

```swift
// WRONG: returning a managed object across boundaries
let user = try await context.perform {
    try context.fetch(User.fetchRequest()).first! // NSManagedObject escapes
}
// user is now accessed off the context's queue

// RIGHT: return a DTO or objectID
let dto = try await context.perform {
    try context.fetch(User.fetchRequest()).first!.toDTO()
}
```

---

## DAO Pattern with Actors

A Data Access Object (DAO) actor encapsulates all Core Data operations, ensuring context access is serialized:

```swift
actor UserDAO {
    private let context: NSManagedObjectContext

    init(container: NSPersistentContainer) {
        self.context = container.newBackgroundContext()
    }

    func create(name: String, email: String) async throws -> UserDTO {
        try await context.perform {
            let user = User(context: self.context)
            user.name = name
            user.email = email
            try self.context.save()
            return user.toDTO()
        }
    }

    func fetchAll() async throws -> [UserDTO] {
        try await context.perform {
            let request = User.fetchRequest()
            request.sortDescriptors = [NSSortDescriptor(key: "name", ascending: true)]
            return try self.context.fetch(request).map { $0.toDTO() }
        }
    }

    func update(id: NSManagedObjectID, name: String) async throws -> UserDTO {
        try await context.perform {
            guard let user = try self.context.existingObject(with: id) as? User else {
                throw DataError.notFound
            }
            user.name = name
            try self.context.save()
            return user.toDTO()
        }
    }

    func delete(id: NSManagedObjectID) async throws {
        try await context.perform {
            let user = try self.context.existingObject(with: id)
            self.context.delete(user)
            try self.context.save()
        }
    }
}
```

**Why this works:**
- The actor serializes calls to DAO methods
- `context.perform` ensures Core Data operations run on the context's queue
- Only `Sendable` DTOs cross the actor boundary

### Double Serialization Consideration

Note that both the actor and `context.perform` serialize access. This is intentional — the actor prevents interleaved async calls, and `perform` ensures the context's queue is used. If you find this adds unnecessary overhead, you can use a custom executor (see below).

---

## Custom Executors for Core Data

Swift 5.9+ allows actors to use custom executors. You can make an actor execute directly on a Core Data context's queue, eliminating the need for `perform`:

```swift
actor CoreDataActor {
    private let context: NSManagedObjectContext

    // Use the context's queue as the actor's executor
    nonisolated var unownedExecutor: UnownedSerialExecutor {
        context.unownedExecutor // NSManagedObjectContext conforms to SerialExecutor
    }

    init(container: NSPersistentContainer) {
        self.context = container.newBackgroundContext()
    }

    // No need for context.perform — the actor already runs on the context's queue
    func fetchUsers() throws -> [UserDTO] {
        let request = User.fetchRequest()
        return try context.fetch(request).map { $0.toDTO() }
    }

    func createUser(name: String) throws -> UserDTO {
        let user = User(context: context)
        user.name = name
        try context.save()
        return user.toDTO()
    }
}
```

This works because `NSManagedObjectContext` conforms to `SerialExecutor` (since iOS 17 / macOS 14). The actor runs all its methods on the context's queue directly, so you don't need the `perform` wrapper.

---

## Default MainActor Isolation Conflicts with Core Data

Swift 6 defaults many UI types to `@MainActor`. This creates friction with Core Data because:

1. `NSManagedObjectContext` created on a background queue cannot be used from `@MainActor`
2. `viewContext` is tied to the main queue, which aligns with `@MainActor`, but background contexts do not
3. Performing heavy fetches on `viewContext` (MainActor) blocks the UI

### Common Conflict: ViewModel with Background Work

```swift
// PROBLEM: @MainActor ViewModel trying to use background context
@MainActor
class ItemViewModel: ObservableObject {
    @Published var items: [ItemDTO] = []
    private let backgroundContext: NSManagedObjectContext

    func loadItems() async throws {
        // Cannot call backgroundContext.perform here because
        // backgroundContext is not Sendable across to @MainActor
        // and the perform closure would need to send results back
    }
}
```

### Solution: Use a DAO Actor

```swift
@MainActor
class ItemViewModel: ObservableObject {
    @Published var items: [ItemDTO] = []
    private let dao: ItemDAO // actor

    func loadItems() async throws {
        // Crosses from MainActor to DAO actor
        items = try await dao.fetchAll()
        // DTOs are Sendable, so this is safe
    }
}
```

### Solution: Use viewContext for Reads, Background for Writes

```swift
@MainActor
class ItemViewModel: ObservableObject {
    @Published var items: [Item] = [] // managed objects on main context
    private let viewContext: NSManagedObjectContext
    private let writeDAO: ItemDAO

    func loadItems() throws {
        // Synchronous fetch on viewContext is fine on MainActor
        let request = Item.fetchRequest()
        items = try viewContext.fetch(request)
    }

    func deleteItem(_ item: Item) async throws {
        let objectID = item.objectID
        try await writeDAO.delete(id: objectID) // background write

        // Refresh viewContext after background write
        // (use NSManagedObjectContextDidSave notification or manual refresh)
        try loadItems()
    }
}
```

---

## SwiftData and Concurrency

SwiftData (introduced alongside iOS 17) was built with Swift Concurrency in mind.

### ModelActor

`@ModelActor` creates an actor with its own `ModelContext`, similar to the Core Data custom executor pattern:

```swift
@ModelActor
actor UserStore {
    func fetchAll() throws -> [UserModel] {
        let descriptor = FetchDescriptor<UserModel>(
            sortBy: [SortDescriptor(\.name)]
        )
        return try modelContext.fetch(descriptor)
    }

    func create(name: String) throws {
        let user = UserModel(name: name)
        modelContext.insert(user)
        try modelContext.save()
    }

    func delete(_ id: PersistentIdentifier) throws {
        guard let user = modelContext.model(for: id) as? UserModel else { return }
        modelContext.delete(user)
        try modelContext.save()
    }
}
```

The `@ModelActor` macro generates the actor with a custom executor tied to the `ModelContext`'s queue.

### PersistentIdentifier as the Sendable Token

In SwiftData, `PersistentIdentifier` serves the same role as `NSManagedObjectID` — it is `Sendable` and can be passed across isolation boundaries:

```swift
@MainActor
class ViewModel: ObservableObject {
    @Published var users: [UserDTO] = []
    let store: UserStore

    func deleteUser(id: PersistentIdentifier) async throws {
        try await store.delete(id)
        await refresh()
    }
}
```

### SwiftData Models and Sendability

SwiftData `@Model` classes are **not Sendable**, just like `NSManagedObject`. The same rules apply:

- Do not pass model instances across isolation boundaries
- Use `PersistentIdentifier` or plain `Sendable` structs
- Access models only from the `ModelContext` that owns them

### @Query in SwiftUI

The `@Query` property wrapper in SwiftUI handles observation automatically and is MainActor-safe:

```swift
struct UserListView: View {
    @Query(sort: \.name) private var users: [UserModel]

    var body: some View {
        List(users) { user in
            Text(user.name)
        }
    }
}
```

`@Query` runs on the view's `ModelContext` (which is on the main actor) and updates the view reactively.
