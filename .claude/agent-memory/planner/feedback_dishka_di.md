---
name: Dishka DI migration preference
description: User wants to migrate from plain Python constructor DI (Services dataclass) to dishka library for .NET-style constructor injection
type: feedback
---

Replace the hand-rolled Services frozen dataclass + manual handler registration with dishka DI container.

**Why:** User wants auto-wiring via type hints (similar to .NET constructor injection), scope management, and reduced boilerplate. The current pattern requires 118 lines of manual handler construction and a 73-line god dataclass.

**How to apply:** When planning or implementing DI changes in PocketQuant, use dishka patterns: Provider classes with `@provide` decorators, `FromDishka[]` in routes, `DishkaRoute` on routers, async generator factories for lifecycle management. Plan is at `plans/260313-1212-dishka-di-refactor/`.
