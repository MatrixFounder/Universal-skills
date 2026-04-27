# Sequence diagram fixture

Three-actor sequence with `alt` and `loop` blocks. Exercises mmdc's
sequence renderer (which has a different layout engine than the
flowchart renderer used by `graph LR`).

```mermaid
sequenceDiagram
    actor User
    participant API
    participant DB

    User->>API: POST /orders
    activate API
    API->>DB: INSERT order
    activate DB
    DB-->>API: ok (id=42)
    deactivate DB

    alt payment ok
        API->>DB: UPDATE status=paid
        DB-->>API: ok
    else payment failed
        API->>DB: DELETE order
        DB-->>API: ok
    end

    loop every 30s
        API->>DB: SELECT pending
        DB-->>API: rows
    end

    API-->>User: 201 Created
    deactivate API
```
