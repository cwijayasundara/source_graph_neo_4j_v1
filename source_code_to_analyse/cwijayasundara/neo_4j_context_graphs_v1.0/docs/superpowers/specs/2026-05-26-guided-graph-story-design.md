# Guided Graph Story Design

## Goal

Make the Graph page readable by default while keeping the full Neo4j graph explorable. The current all-data visualization can render thousands of nodes and relationships at once, which makes the graph visually dense and hard to interpret. The new default should present a guided financial story first, then let the user expand outward when they need more context.

## Default Experience

The Graph page opens in a curated finance narrative rather than a full database dump:

`Person -> Account -> Statement -> Transaction -> Merchant -> Category -> TimePeriod`

The first screen should show a bounded slice of this path. It should include the account owner, accounts, recent or representative statements, a limited set of transactions, connected merchants, categories, and time periods. This gives the user an immediate mental model of how their financial data is represented in Neo4j.

The full graph remains available through an explicit exploration mode, but it is not the default view.

## User Interface

The page should be organized as a work surface with three clear areas:

- A left rail of story presets: Overview, Accounts, Spending, Merchants, Categories, Statements, and Explore All.
- A central graph canvas focused on the selected story slice.
- A right details panel showing selected node or relationship properties.

The left rail should use compact controls, not explanatory marketing text. Each preset changes the graph slice and summary counts. The central graph should emphasize entity type, direction, and path readability with stronger captions, clearer colors, and more deliberate node sizing. The details panel should keep the existing property inspection behavior but make the selected entity easier to understand.

## Presets

Overview shows the finance path from owner to accounts to statements and sampled transactions.

Accounts focuses on account ownership, institutions, latest balances, and statements.

Spending focuses on transactions, merchants, categories, and time periods.

Merchants focuses on merchant clusters and linked categories.

Categories focuses on category hierarchy plus the connected merchants and transaction totals.

Statements focuses on statement periods and their contained transactions.

Explore All exposes the broader Neo4j graph with label filters and search. This preserves access to memory, documents, traces, conversations, and other context-graph data without overwhelming the default page.

## Backend Data Shape

Add or extend graph endpoints so the frontend can request a named story slice rather than always receiving the whole graph. The response should continue using the existing graph shape:

- `nodes`
- `relationships`
- optional `results` for compatibility

Each slice should return bounded results with sensible defaults and optional query parameters for limits. The backend should compute useful aggregate properties where they improve readability, such as transaction counts, total spend, latest balance, active months, or category totals.

## Frontend Data Flow

The graph page owns the selected preset and requests the matching graph slice. `ContextGraphView` remains the renderer, but it should receive smaller, intentional data sets. Existing node selection, relationship selection, schema mode, and double-click expansion should continue to work.

The frontend should not filter a huge all-data payload in memory as the primary path. Filtering should happen at the API level so the page stays responsive as the graph grows.

## Interaction Behavior

Clicking a node selects it and opens the details panel.

Double-clicking a node expands immediate neighbors using the existing expansion behavior.

Switching presets replaces the current graph slice and clears selection.

Explore All gives access to full graph/schema exploration for advanced inspection.

## Visual Rules

The graph should prioritize readability over density:

- show fewer nodes by default
- make important finance entities larger
- use distinct colors for Account, Statement, Transaction, Merchant, Category, Person, Institution, and TimePeriod
- keep relationship captions visible only when useful
- avoid rendering every transaction unless the user explicitly expands or switches into a high-detail view

This follows the create-context-graph idea: the value is in meaningful entity paths and context retrieval, not in showing every node simultaneously.

## Error Handling

If a preset returns no data, show an empty state specific to that preset with an action to switch to Explore All or rerun ingestion.

If a slice request fails, show the failed preset name and the backend error message.

If graph rendering fails, keep the page shell visible and show a recoverable graph visualization error.

## Testing

Backend tests should cover at least one story slice, including nodes, relationships, and aggregate properties.

Frontend build/type checks must pass.

If feasible, add a focused frontend test or component-level check for switching presets and rendering non-empty graph data.

Manual verification should include loading the Graph page, confirming the Overview preset is visible by default, switching at least two presets, selecting a node, and expanding a node.
