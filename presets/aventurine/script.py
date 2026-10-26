"""Aventurine Trafficking automation for Honkai: Star Rail.

Ported from the reference implementation to the async Context API.

NOTE: Coordinates and landmarks in preset.json are calibrated for 3840x2160.
If your resolution differs, the auto-scaler adjusts ROIs but you may still
need to recalibrate landmarks (especially the flush button) manually.
"""

from cvauto.core.context import Context


async def run(ctx: Context) -> None:
    state = "normal"
    bail_count = 0

    while ctx.running:
        matches = await ctx.next_frame()

        # ----- parse deck ------------------------------------------------
        deck_total = 0
        found1: list = []
        found2: list = []
        found3: list = []

        deck = matches.get("deck", {})
        if "deck_1star" in deck:
            found1 = deck["deck_1star"]
            deck_total += len(found1)
        if "deck_2star" in deck:
            found2 = deck["deck_2star"]
            deck_total += 3 * len(found2)
        if "deck_3star" in deck:
            found3 = deck["deck_3star"]
            deck_total += 9 * len(found3)

        # ----- parse shop ------------------------------------------------
        found_store: list = []
        shop = matches.get("shop", {})
        if "store" in shop:
            found_store = shop["store"]

        ctx.log(f"1-Star count: {deck_total}")

        # ----- bail-out condition ----------------------------------------
        # 2x 2-star + 1x 1-star and shop has 0 or 1 cards => flush
        if len(found2) == 2 and len(found1) == 1 and len(found_store) <= 1:
            ctx.log("Deck full, bail out")
            if state == "normal":
                ctx.click("flush_button")
                await ctx.sleep(0.1)
            else:
                if bail_count > 50:
                    state = "normal"
                    bail_count = 0
                    ctx.click("flush_button")
                    await ctx.sleep(0.1)
                else:
                    bail_count += 1
                    await ctx.sleep(0.05)
            continue

        # ----- sell 3-star -----------------------------------------------
        if deck_total >= 9 and found3:
            ctx.log("Sell three star")
            match = found3[0]
            cx, cy = match.center
            ctx.move(cx, cy)
            await ctx.sleep(0.1)
            ctx.mouse_down()
            await ctx.sleep(0.1)
            ctx.move(0, cy)
            await ctx.sleep(0.1)
            ctx.mouse_up()
            await ctx.sleep(0.4)
            if state == "wait_sell":
                state = "normal"
            continue

        # ----- buy cards -------------------------------------------------
        if found_store:
            for match in found_store:
                ctx.click(match.center)
                await ctx.sleep(0.25)

            # If buying creates a 3-star, wait for synthesis animation.
            if deck_total + len(found_store) >= 9:
                await ctx.sleep(0.8)
                state = "wait_sell"
            else:
                ctx.move(0, 0)
                can_combine = (
                    len(found1) == 2 and len(found_store) != 0
                    or len(found1) == 1
                       and (len(found1) + len(found2) + len(found3)) < 3
                       and len(found_store) >= 2
                    or deck_total == 0 and len(found_store) >= 3
                )
                if can_combine:
                    await ctx.sleep(2.5)
            continue

        # ----- flush if shop empty ---------------------------------------
        if state == "normal":
            ctx.click("flush_button")
            await ctx.sleep(0.1)

        await ctx.sleep(0.01)
