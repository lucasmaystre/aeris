# Agent-Friendly Notes Application

## 1. Project Overview

I am building a personal notes application designed for two primary modes of interaction:

1. **Human interaction:** A convenient web interface for creating, editing, browsing, and searching notes.
2. **Agent interaction:** A command-line interface that AI agents can use to search, retrieve, and create notes programmatically.

The overarching goal is to create a simple, fast, and agent-friendly system for managing a personal knowledge base.

I already have a PostgreSQL database hosted on Neon and a working CLI. The next steps are to build the web interface, implement search, and establish a clean architecture that supports both interfaces without unnecessary duplication.

At this stage, I want to explore architectural options, technology choices, and appropriate abstractions before committing to a specific implementation.

## 2. Existing Components

### 2.1 Database

**Status: Implemented**

I currently use NeonDB (PostgreSQL) to store notes.

The database has a simple `notes` table containing approximately:

- A creation date
- A last-updated timestamp
- The note content

Notes are typically written in Markdown, although the database can treat their content as plain text.

The database schema is intentionally minimal.

### 2.2 Command-Line Interface

**Status: Implemented**

I have built a CLI that interacts with the database.

Its functionality includes:

- Listing notes
- Displaying an individual note
- Creating and saving new notes
- Opening a terminal editor, such as Vim, for writing notes

The CLI is intended for both personal use and programmatic use by AI agents.

One important goal is to make it easy for an agent to retrieve relevant information from the notes database and load specific notes into its context while completing a task.

## 3. Planned Web Interface

**Status: First version implement with htmx**

I want to build a web application for interacting with the same notes database.

The interface should support:

- Browsing and listing notes
- Viewing individual notes with rendered Markdown
- Creating new notes
- Editing existing notes
- Searching across notes
- Quickly navigating between search results

I am interested in deploying the application using **Vercel**, while continuing to use NeonDB as the PostgreSQL backend.

An important architectural question is whether the web application should access the database directly through server-side code or communicate with a shared backend service.

## 4. Search Requirements

Search is a critical feature that I have not yet implemented.

I want to support two distinct search modes.

### 4.1 Exact Substring Search

**Priority: Critical**

I want extremely fast text search across note contents.

In particular, the web interface should have a search box that filters the list of notes interactively as I type.

Desired behavior:

- Search for notes containing the exact substring entered by the user.
- Support sensible normalization, particularly case-insensitive matching.
- Update results with very low latency, ideally on every keystroke.
- Handle partial queries naturally.
- Return matching notes in a way that supports rapid browsing.

For example, if I type `distributed systems`, I want to see notes containing that exact phrase, regardless of capitalization.

**Performance is a primary requirement.** The experience should feel instantaneous.

I want to understand which PostgreSQL indexing strategies, query patterns, or other technologies are appropriate for this use case.

### 4.2 Semantic Similarity Search

**Priority: Critical**

I also want semantic search using embeddings.

Rather than searching for an exact string, I want to express a natural-language query and retrieve notes that are conceptually related to it.

For example:

*Query: "What have I written about making AI agents more reliable?"*

The system should return approximately the ten most relevant notes, even if those notes do not contain the exact words used in the query.

Desired behavior:

- Generate embeddings for notes.
- Generate an embedding for a search query.
- Retrieve the top-k semantically similar notes, typically around ten.
- Return the relevant notes or identifiers so that the user or an agent can retrieve their full contents.

I want to investigate whether this can be implemented efficiently within Neon/PostgreSQL, potentially using vector search extensions, without introducing additional infrastructure.

## 5. Agent-Friendly Design

Agent compatibility is a core design principle, not an afterthought.

The CLI should provide a simple, reliable interface through which an AI agent can:

1. Search the notes database using an exact string or semantic query.
2. Identify relevant notes from search results.
3. Retrieve the full contents of specific notes.
4. Potentially create or update notes as part of a workflow.

A typical agent workflow might be:

**User task → Agent searches notes → Agent identifies relevant notes → Agent retrieves note contents → Agent uses those notes as context to complete the task.**

I want to ensure that the CLI is easy for agents to invoke and that its output can be consumed programmatically.

Ideally, the architecture will also make it straightforward to expose the same functionality through other agent integrations in the future.

## 6. Architectural Questions

The biggest unresolved issue is how to structure the project.

### 6.1 Shared Logic Between CLI and Web UI

Both interfaces will need to perform many of the same operations:

- List notes
- Read notes
- Create notes
- Update notes
- Search notes using exact substring matching
- Search notes using semantic similarity

I want to avoid implementing the same database access logic and business logic twice.

Questions to explore:

- Should both interfaces depend on a shared library?
- Should there be a common backend API?
- Should the CLI access PostgreSQL directly while the web UI uses server-side API routes?
- What belongs in a database access layer versus a service layer?
- How much abstraction is justified for a relatively small personal application?

I want an architecture that is clean and maintainable without becoming unnecessarily complicated.

### 6.2 Database and Search Architecture

I want to understand:

- How to implement fast, case-insensitive substring search in PostgreSQL.
- Whether PostgreSQL's built-in text search features are appropriate.
- Whether additional indexes or extensions are necessary.
- How to implement embedding-based similarity search.
- How to store and update embeddings when notes change.
- Whether exact and semantic search should share an interface or remain distinct capabilities.

### 6.3 Web Application Architecture

Questions include:

- Which web framework should I use?
- Is Next.js a good fit given my interest in Vercel?
- Should the web application communicate directly with NeonDB through server-side code?
- Do I need a separate backend service?
- How should the frontend manage note editing, Markdown rendering, and search?
- How can I minimize latency for interactive search?

### 6.4 Agent Integration

I also want to consider:

- What CLI command structure would be most useful for agents?
- Should commands support structured JSON output?
- Should semantic search return full notes, summaries, snippets, or identifiers?
- Would the design benefit from supporting MCP or other agent-facing protocols later?
- How do I keep the agent interface stable as the application evolves?

## 7. Technology Preferences and Constraints

| Component                | Current preference               | Status                |
| ------------------------ | -------------------------------- | --------------------- |
| Database                 | NeonDB / PostgreSQL              | Existing              |
| Note format              | Markdown                         | Existing              |
| CLI                      | Existing implementation          | Working               |
| Web hosting              | Vercel                           | Preferred             |
| Web framework            | To be determined                 | Open                  |
| Exact search             | Very fast substring matching     | To design             |
| Semantic search          | Embeddings and vector similarity | To design             |
| Shared application logic | Minimal reusable abstractions    | To design             |
| Agent interface          | CLI-first, extensible            | Partially implemented |

### Design priorities

The architecture should emphasize:

1. **Performance:** Particularly low-latency interactive substring search.
2. **Simplicity:** Avoid services and abstractions that are not clearly necessary.
3. **Code reuse:** Share relevant functionality between the CLI and web interfaces.
4. **Agent compatibility:** Make data retrieval straightforward for AI agents.
5. **Maintainability:** Keep the codebase easy to understand and evolve.
6. **Infrastructure reuse:** Prefer leveraging Neon/PostgreSQL and Vercel before adding more infrastructure.

## 8. Desired Outcome of the Design Discussion

I am not looking to start implementing everything immediately.

I would first like to develop a lightweight technical design document that provides:

- A recommended high-level architecture
- Clear boundaries between application layers
- A proposed codebase and package structure
- Technology recommendations and their trade-offs
- A concrete approach to exact substring search
- A concrete approach to semantic similarity search
- A strategy for maintaining note embeddings
- A proposed interface shared by the CLI and web application
- An incremental implementation plan

The goal is to arrive at an architecture that is fast, elegant, practical, and appropriately scoped for a personal notes application that is equally useful to humans and AI agents.

## 9. Central Design Question

**What is the simplest architecture that allows a web UI and an agent-friendly CLI to share a Neon/PostgreSQL-backed notes database while supporting extremely fast substring search, semantic similarity search, and Markdown editing?**

That is the primary question I want the design discussion to answer.

