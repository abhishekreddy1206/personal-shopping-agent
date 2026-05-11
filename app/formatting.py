from __future__ import annotations

from typing import Any, Dict


def format_result(payload: Dict[str, Any]) -> str:
    intent_type = payload.get("intent_type")
    if intent_type == "history_lookup":
        searches = payload.get("recent_searches", [])
        if not searches:
            return "No recent searches yet."
        lines = ["Recent searches:"]
        seen = set()
        for item in searches:
            key = (item.get("raw_query"), item.get("status"))
            if key in seen:
                continue
            seen.add(key)
            lines.append("- {raw_query} [{status}]".format(**item))
            if len(lines) >= 6:
                break
        return "\n".join(lines)

    if intent_type == "watchlist_view":
        items = payload.get("watch_items", [])
        if not items:
            return "Your watchlist is empty."
        lines = ["Watchlist:"]
        seen = set()
        for item in items:
            key = (item.get("normalized_subject"), item.get("target_price"))
            if key in seen:
                continue
            seen.add(key)
            price = item.get("target_price")
            suffix = " below ${}".format(price) if price is not None else ""
            label = item.get("user_label") or item.get("normalized_subject") or "Unnamed watch"
            lines.append("- {}{}".format(label, suffix))
            if len(lines) >= 6:
                break
        return "\n".join(lines)

    if intent_type == "watch_create":
        lines = [payload.get("message") or "Watch item created."]
        items = payload.get("watch_items", [])
        if items:
            top = items[0]
            label = top.get("user_label") or top.get("normalized_subject")
            lines.append("Tracking: {}".format(label))
            if top.get("target_price") is not None:
                lines.append("Target price: ${}".format(top.get("target_price")))
        return "\n".join(lines)

    results = payload.get("results", [])
    budget_summary = payload.get("budget_summary") or {}
    lane_summary = payload.get("lane_summary") or budget_summary.get("lane_summary") or {}
    if not results:
        lines = []
        if payload.get("source_mode"):
            lines.append("Mode: {}".format(payload.get("source_mode")))
        lines.append(payload.get("message") or "No results.")
        trusted = lane_summary.get("cheapest_trusted_retail")
        market = lane_summary.get("cheapest_marketplace")
        overall = lane_summary.get("best_overall_value")
        if trusted:
            lines.append("Trusted retail best: {} — {} — ${}".format(trusted.get("title"), trusted.get("retailer"), trusted.get("effective_price")))
        if market:
            lines.append("Marketplace best: {} — {} — ${}".format(market.get("title"), market.get("retailer"), market.get("effective_price")))
        if overall:
            lines.append("Best overall value: {} — {} — ${}".format(overall.get("title"), overall.get("retailer"), overall.get("effective_price")))
        if budget_summary.get("applied") and budget_summary.get("lowest_over_budget"):
            lowest = budget_summary.get("lowest_over_budget") or {}
            lines.append(
                "Closest over budget: {} — {} — ${}".format(
                    lowest.get("title"),
                    lowest.get("retailer"),
                    lowest.get("effective_price"),
                )
            )
        return "\n".join(lines)

    lines = []
    if payload.get("source_mode"):
        lines.append("Mode: {}".format(payload.get("source_mode")))
    lines.append(payload.get("message") or "Results:")
    trusted = lane_summary.get("cheapest_trusted_retail")
    market = lane_summary.get("cheapest_marketplace")
    overall = lane_summary.get("best_overall_value")
    if trusted:
        lines.append("Trusted retail best: {} — {} — ${}".format(trusted.get("title"), trusted.get("retailer"), trusted.get("effective_price")))
    if market:
        lines.append("Marketplace best: {} — {} — ${}".format(market.get("title"), market.get("retailer"), market.get("effective_price")))
    if overall:
        lines.append("Best overall value: {} — {} — ${}".format(overall.get("title"), overall.get("retailer"), overall.get("effective_price")))
    for item in results[:5]:
        price = item.get("effective_price")
        price_text = "${}".format(price) if price is not None else "price unknown"
        confidence = item.get("confidence") or "unknown"
        lane = item.get("lane") or "unknown"
        role = item.get("source_role") or "unknown"
        verification = item.get("verification_state") or "unknown"
        condition = item.get("condition") or item.get("condition_display") or "unknown"
        badge = _lane_badge(lane)
        lines.append(
            "- {} {} — {} — {} [{} | {} | {} | {}]".format(
                badge,
                item.get("title"),
                item.get("retailer"),
                price_text,
                role,
                verification,
                condition,
                confidence,
            )
        )
        enrichment = item.get("enrichment") or {}
        pending = [name for name, state in enrichment.items() if state.get("status") != "connected"]
        if pending:
            lines.append("  enrichment: {} not connected".format(", ".join(sorted(pending))))
    return "\n".join(lines)


def format_watch_check(payload: Dict[str, Any]) -> str:
    results = payload.get("watch_check_results", [])
    if not results:
        return "No active watch items produced check results."
    lines = ["Watch check results:"]
    seen = set()
    for item in results:
        best = item.get("best_offer")
        alerts = item.get("alerts", [])
        key = (item.get("normalized_subject") or item.get("query"), best.get("retailer") if best else None, best.get("effective_price") if best else None)
        if key in seen:
            continue
        seen.add(key)
        label = item.get("query")
        if best:
            lines.append("- {} -> {} at ${} [{}]".format(label, best.get("retailer"), best.get("effective_price"), best.get("confidence")))
        for alert in alerts:
            lines.append("  Alert: {} (target ${}, current ${})".format(alert.get("type"), alert.get("target_price"), alert.get("current_price")))
        if len(lines) >= 10:
            break
    return "\n".join(lines)


def _lane_badge(lane: str) -> str:
    return {
        "trusted_retail": "[retail]",
        "discovery": "[discovery]",
        "marketplace": "[market]",
    }.get(lane, "[source]")
