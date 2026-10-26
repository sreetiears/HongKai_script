# Async/await plugin API

We chose an async/await entry point (`async def run(ctx: Context)`) as the contract between the framework and automation scripts, instead of the class-based callback pattern used by CvAutomation (`on_frame(matches)`).

The class-based model inverts control: the framework calls the script every frame, forcing all logic into a single callback. Sequential flows ("click, wait 2s, click again") become timer variables and state checks. It also risks blocking the capture loop unless every plugin runs in its own thread.

Async/await gives the script linear, sequential control while the framework regains control at every `await` point. This lets us enforce FPS limits, pause/resume, and inject kill switches without threading complexity. The trade-off is requiring asyncio literacy from plugin authors and bridging the Qt event loop with asyncio, which is well-documented but non-trivial.

We explicitly considered and rejected:
- **Class-based callbacks** — inverts control, hard to write sequential logic, blocking risk.
- **Decorator-based state machines** — too rigid for the nested conditional logic typical of game automation (e.g. the Aventurine card-shop heuristic).
